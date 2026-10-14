"""Tests for the security-advisories behavior: GitHub repository security advisories recorded once as work.

gh and basecamp are stubbed; nothing touches the network.
"""
import json, os, sys, unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_tools import TodoStub, ToolBase  # noqa: E402
import behaviors  # noqa: E402

REPO = "acme/server"


def advisory(ghsa="GHSA-aaaa-bbbb-cccc", state="triage", severity="high", at="2026-10-01T00:00:00Z"):
    return {"ghsa_id": ghsa, "state": state, "severity": severity, "summary": "Token leak in OAuth redirect",
            "created_at": at, "html_url": f"https://github.com/{REPO}/security/advisories/{ghsa}",
            "author": {"login": "someone"}, "credits_detailed": [{"type": "reporter", "user": {"login": "finder"}}]}


class GhStub(TodoStub):
    def __init__(self):
        super().__init__()
        self.advisories, self.denied, self.gh = {REPO: []}, {}, []

    def __call__(self, cmd, **kw):
        if cmd[0] == "gh":
            self.gh.append(cmd)
            repo = cmd[2].split("/security-advisories")[0][len("repos/"):]
            if repo in self.denied:
                return SimpleNamespace(stdout=json.dumps({"message": "Not Found"}), returncode=1,
                                       stderr=f"gh: Not Found (HTTP {self.denied[repo]})")
            return SimpleNamespace(stdout=json.dumps(self.advisories.get(repo, [])), stderr="", returncode=0)
        return super().__call__(cmd, **kw)


class Advisories(ToolBase):
    def setUp(self):
        super().setUp()
        self.stub = GhStub()
        self.cfg(advisories={"repos": [REPO]})

    def run_once(self, dry=False):
        p = os.path.join(self.cfgdir, "timer.json")
        if os.path.exists(p):
            os.remove(p)  # every behavior due, as on its cadence
        self.poll(dry=dry)

    def adv(self):
        return [r for r in self.pending() if r["kind"].startswith("advisory")]

    def test_off_by_default_and_hourly(self):
        self.cfg(drop=("advisories",))
        self.run_once()
        self.assertEqual(self.stub.gh, [])
        self.cfg(advisories={"repos": [REPO]})
        self.assertEqual(self.sync().behaviors["security-advisories"].runs, "hourly")

    def test_malformed_config_refused(self):
        for bad in ({}, {"repos": "acme/server"}, {"repos": ["server"]}, []):
            self.cfg(advisories=bad)
            with self.assertRaises(ValueError):
                self.sync()

    def test_triage_and_draft_recorded_once_published_and_closed_ignored(self):
        self.stub.advisories[REPO] = [advisory(), advisory("GHSA-dddd-eeee-ffff", "draft", None),
                                      advisory("GHSA-old1-old1-old1", "published"), advisory("GHSA-old2-old2-old2", "closed")]
        self.run_once()
        self.run_once()
        self.assertEqual([(r["kind"], r["ghsa"], r["state"]) for r in self.adv()],
                         [("advisory", "GHSA-aaaa-bbbb-cccc", "triage"), ("advisory", "GHSA-dddd-eeee-ffff", "draft")])
        rec = self.adv()[0]
        self.assertEqual((rec["repo"], rec["severity"], rec["reporter"], rec["created_at"], rec["url"]),
                         (REPO, "high", "finder", "2026-10-01T00:00:00Z",
                          f"https://github.com/{REPO}/security/advisories/GHSA-aaaa-bbbb-cccc"))
        self.assertEqual(self.stub.gh[0], ["gh", "api", f"repos/{REPO}/security-advisories?per_page=100"])

    def test_publish_or_close_is_one_follow_up_and_triage_to_draft_is_quiet(self):
        a, b = advisory(), advisory("GHSA-dddd-eeee-ffff")
        self.stub.advisories[REPO] = [a, b]
        self.run_once()
        a["state"], b["state"] = "draft", "closed"
        self.run_once()
        a["state"] = "published"
        self.run_once()
        self.run_once()
        self.assertEqual([(r["kind"], r["ghsa"], r["state"], r.get("previous")) for r in self.adv()],
                         [("advisory", "GHSA-aaaa-bbbb-cccc", "triage", None),
                          ("advisory", "GHSA-dddd-eeee-ffff", "triage", None),
                          ("advisory-update", "GHSA-dddd-eeee-ffff", "closed", "triage"),
                          ("advisory-update", "GHSA-aaaa-bbbb-cccc", "published", "draft")])

    def test_unreadable_repo_reported_once_until_readable_again(self):
        self.stub.denied[REPO] = "404"
        self.run_once()
        self.run_once()
        self.assertEqual([(r["kind"], r["repo"], r["status"]) for r in self.adv()], [("advisory-unreadable", REPO, "404")])
        self.assertEqual(open(os.path.join(self.cfgdir, "sync.log")).read().count("reported once"), 1)
        del self.stub.denied[REPO]
        self.stub.advisories[REPO] = [advisory()]
        self.run_once()
        self.stub.denied[REPO] = "403"
        self.run_once()
        self.assertEqual([r["kind"] for r in self.adv()], ["advisory-unreadable", "advisory", "advisory-unreadable"])

    def test_dry_run_records_nothing(self):
        self.stub.advisories[REPO] = [advisory()]
        self.run_once(dry=True)
        self.assertEqual(self.adv(), [])
        self.assertFalse(os.path.exists(os.path.join(self.cfgdir, "advisories.json")))
        self.run_once()
        self.assertEqual(len(self.adv()), 1)

    def test_delivered_as_an_inbox_note_in_the_same_run(self):
        self.cfg(inbox={})
        self.run_once()
        self.stub.advisories[REPO] = [advisory()]
        self.run_once()
        self.run_once()
        [(rid, body, _, _)] = [n for n in self.stub.notes if "advisory" in n[0]]
        self.assertEqual(rid, "basecamp-advisory-acme-server-GHSA-aaaa-bbbb-cccc")
        self.assertIn("GitHub security advisory GHSA-aaaa-bbbb-cccc on acme/server in triage, severity high", body)
        self.assertIn("never change the advisory's state, publish it or comment on it without the captain's word", body)


class Note(unittest.TestCase):
    def test_update_and_unreadable_notes(self):
        rid, body = behaviors.inbox_note({"kind": "advisory-update", "repo": REPO, "ghsa": "GHSA-x", "state": "published",
                                          "previous": "triage", "summary": "Leak"}, "1", "2")
        self.assertEqual(rid, "basecamp-advisory-update-acme-server-GHSA-x-published")
        self.assertIn("moved from triage to published", body)
        rid, body = behaviors.inbox_note({"kind": "advisory-unreadable", "repo": REPO, "status": "403"}, "1", "2")
        self.assertEqual(rid, "basecamp-advisory-unreadable-acme-server")
        self.assertIn("cannot be read by this login (HTTP 403)", body)


if __name__ == "__main__":
    unittest.main()
