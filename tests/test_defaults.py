"""Tests for the workflow defaults file: the shipped prompts/defaults.md holds the workflow the base prompt used to fix,
init copies it beside the config once and never overwrites it, the backup keeps it, and doctor flags a home without it.

The basecamp CLI and systemd are stubbed; nothing touches the network.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_backup  # noqa: E402
import test_sync  # noqa: E402
import test_init  # noqa: E402
import test_setup  # noqa: E402
import behaviors  # noqa: E402
import init_home  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shipped(name):
    with open(os.path.join(ROOT, "prompts", name)) as f:
        return f.read()


class Shipped(unittest.TestCase):
    def test_the_workflow_moved_from_the_base_prompt_into_the_defaults(self):
        defaults, base = shipped("defaults.md"), shipped("base.md")
        for policy in ("## Where things go", "Answer every line", "## Decisions", "--subtask", "## Check-ins",
                       "## Reports", "## Unmonitored input", "unmonitored handle", "**Scheduled to-dos.**",
                       "**Records from a participant**", "route the fix the same day"):
            self.assertIn(policy, defaults)
        for gone in ("Answer every line", "## 3. Decision to-dos", "Post each investigation report"):
            self.assertNotIn(gone, base)
        self.assertIn("HOME/data/basecamp-sync/defaults.md", base)
        self.assertIn("## 4. Bounds", base)


class Notes(unittest.TestCase):
    """An inbox note says what happened, the facts and the commands; how to handle it is the home's defaults."""
    RECORDS = [
        {"kind": "chat-question", "line": 2, "text": "ship it?", "captain": True},
        {"kind": "todo-comment", "key": "k", "comment": 3, "captain": True},
        {"kind": "todo-request", "key": "request-4", "todo": 4, "captain": True, "due_on": "2026-11-01"},
        {"kind": "todo-request-closed", "key": "request-4", "todo": 4, "reason": "unassigned", "captain": True},
        {"kind": "unmonitored", "key": "comment.created/Document", "notification": 9, "captain": True},
        {"kind": "advisory", "repo": "o/r", "ghsa": "GHSA-1", "state": "triage"},
        {"kind": "dependabot-alert", "repo": "o/r", "number": 1, "severity": "high"},
        {"kind": "checkin", "question": 5, "date": "2026-10-23", "captain": True},
        {"kind": "mention", "comment": 6, "author": {"id": 1, "name": "Mate"}, "captain": False, "role": "participant"},
    ]

    def test_facts_and_commands_and_never_the_handling(self):
        for rec in self.RECORDS:
            body = behaviors.inbox_note(rec, "1", "2")[1]
            self.assertIn("Handle it as this home's Basecamp defaults say (data/basecamp-sync/defaults.md)", body)
            for advice in ("route", "file a to-do", "put it to the captain", "take it on", "act on it", "weigh",
                           "tell the captain", "never create", "stop the work"):
                self.assertNotIn(advice, body, (rec["kind"], advice))

    def test_the_commands_and_facts_that_matter_stay(self):
        notes = [behaviors.inbox_note(rec, "1", "2")[1] for rec in self.RECORDS]
        self.assertIn("Commands: sync.py reply --recording 2 (answers in the chat).", notes[0])
        self.assertIn("due 2026-11-01 as read now; Basecamp owns the date", notes[2])
        self.assertIn("no longer tracked; there is nothing to complete", notes[3])
        self.assertIn("sync.py unmonitored handle --key 'comment.created/Document'", notes[4])
        self.assertIn("one answer a day", notes[7])
        self.assertIn("their word never authorizes a decision or approval", notes[8])


class Seed(unittest.TestCase):
    setUp, tearDown, init = test_init.InitTest.setUp, test_init.InitTest.tearDown, test_init.InitTest.init

    def path(self):
        return os.path.join(self.dir, "defaults.md")

    def test_init_copies_the_shipped_defaults_once_and_never_overwrites_them(self):
        self.init().main()
        with open(self.path()) as f:
            self.assertEqual(f.read(), shipped("defaults.md"))
        with open(self.path(), "w") as f:
            f.write("# Ours\n\nDecisions go to the Ops project.\n")
        done = self.init().main()
        with open(self.path()) as f:
            self.assertEqual(f.read(), "# Ours\n\nDecisions go to the Ops project.\n")
        self.assertFalse(any("defaults" in d for d in done))

    def test_a_dry_run_plans_the_copy_and_writes_nothing(self):
        plan = self.init(dry=True).main()
        self.assertTrue(any(p.startswith("copy the shipped workflow defaults") for p in plan))
        self.assertFalse(os.path.exists(self.path()))

    def test_the_shipped_file_is_the_one_init_copies(self):
        self.assertEqual(init_home.DEFAULTS, os.path.join(ROOT, "prompts", "defaults.md"))


class Backed(test_sync.Base):
    cfg, backup = test_backup.Backup.cfg, test_backup.Backup.backup

    def test_the_backup_keeps_the_homes_defaults(self):
        self.stub = test_backup.FolderStub()
        self.cfg(backup=test_backup.BACKUP)
        with open(os.path.join(self.cfgdir, "defaults.md"), "w") as f:
            f.write("# Ours\n")
        self.backup()
        self.assertEqual(sorted(os.path.basename(a[2]) for a in self.stub.made("uploads create")),
                         ["config.json", "defaults.md"])


class Doctor(test_setup.Base):
    doctor, healthy = test_setup.DoctorTest.doctor, test_setup.DoctorTest.healthy

    def test_a_home_without_defaults_is_flagged(self):
        self.healthy()
        self.assertEqual(self.doctor(), 0, self.text())
        self.assertIn("workflow defaults", self.text())
        os.remove(os.path.join(os.path.dirname(self.config), "defaults.md"))
        self.assertNotEqual(self.doctor(), 0)
        self.assertIn("no workflow defaults file", self.text())
        self.assertIn(init_home.DEFAULTS, self.text())


if __name__ == "__main__":
    unittest.main()
