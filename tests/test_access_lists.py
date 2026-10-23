"""Tests for the allow lists beyond the captain, operators and "people": "project_people" (heard in one project only),
"participants": {"company"} (anyone in the company, failing closed when a company cannot be read) and `sync.py access`.

The basecamp CLI is stubbed; nothing touches the network.
"""
import json, os, sys, unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sync import ACTING, CAPTAIN, line  # noqa: E402
from test_notifications import NotifBase, NotifStub, PROJECT, note  # noqa: E402
from test_assigned_todos import OTHER, AssignBase, AssignStub, todo  # noqa: E402
from test_pings import PingBase, ping_line, reading  # noqa: E402
from test_blocked import NEW, said  # noqa: E402
import test_init  # noqa: E402

COMPANY, ELSEWHERE = 4035191, 999  # the captain's company; another one
COLLEAGUE, OUTSIDER, GUEST = 18181818, 19191919, 20202020  # in the company; not; named for one project only


def with_companies(cls):
    """An instance of stub class `cls` whose person records (/people/<id>.json) carry a company and a name."""
    class Companies(cls):
        def __call__(self, cmd, **kw):
            args = cmd[3:-3]
            core = args[2:] if args[:1] == ["-P"] else args
            if (cmd[0] == "basecamp" and core[:2] == ["api", "get"] and core[2].startswith("/people/")
                    and not any(f in " ".join(core) for f in self.fail)):
                self.calls.append(core)
                pid = int(core[2].split("/")[2].split(".")[0])
                data = {"id": pid, "name": f"person-{pid}", "attachable_sgid": f"sgid-{pid}",
                        "company": {"id": self.companies.get(pid, ELSEWHERE), "name": "Co"}}
                return SimpleNamespace(stdout=json.dumps({"ok": True, "data": data}), stderr="", returncode=0)
            return super().__call__(cmd, **kw)

        def people_reads(self, pid):
            return self.calls.count(["api", "get", f"/people/{pid}.json"])
    stub = Companies()
    stub.companies = {CAPTAIN: COMPANY, COLLEAGUE: COMPANY}
    return stub


class Company(NotifBase):
    def setUp(self):
        super().setUp()
        self.stub = with_companies(NotifStub)
        self.stub.lines = {"77": [line(1)]}
        self.cfg(participants={"company": True}, blocked={})
        self.poll()
        self.stub.calls.clear()

    def test_a_colleague_is_a_participant_and_an_outsider_is_not(self):
        self.stub.lines["77"] += [said(2, who=COLLEAGUE, content="when?"), said(3, who=OUTSIDER, content="me?")]
        self.poll()
        self.assertEqual([(r["line"], r["role"]) for r in self.pending()], [(2, "participant")])
        self.assertEqual(self.state("companies.json"), {str(CAPTAIN): COMPANY, str(COLLEAGUE): COMPANY, str(OUTSIDER): ELSEWHERE})

    def test_each_person_is_read_once_a_run_and_never_when_the_creator_names_the_company(self):
        self.stub.lines["77"] += [said(2, who=COLLEAGUE, content="a?"), said(3, who=COLLEAGUE, content="b?"),
                                  dict(said(4, content="c?"), creator={"id": OUTSIDER + 1, "company": {"id": COMPANY}})]
        self.poll()
        self.assertEqual([r["line"] for r in self.pending()], [2, 3, 4])
        self.assertEqual((self.stub.people_reads(COLLEAGUE), self.stub.people_reads(OUTSIDER + 1)), (1, 0))

    def test_a_failed_read_uses_the_last_company_known(self):
        self.stub.lines["77"].append(said(2, who=COLLEAGUE, content="when?"))
        self.poll()
        self.stub.fail.add(f"/people/{COLLEAGUE}.json")
        self.stub.lines["77"].append(said(3, who=COLLEAGUE, content="and now?"))
        self.poll()
        self.assertEqual([r["line"] for r in self.pending()], [2, 3])
        self.assertIn("using the last one known", self.log())

    def test_an_unknown_company_admits_no_one_and_gets_no_automatic_reply(self):
        self.stub.fail.add(f"/people/{OUTSIDER}.json")
        self.stub.lines["77"].append(said(2, who=OUTSIDER))
        self.poll()
        self.assertEqual((self.pending(), self.stub.chat_posts()), ([], []))
        self.assertIn("(no reply: their company could not be checked)", self.log())

    def test_a_company_by_id(self):
        self.cfg(participants={"company": ELSEWHERE})
        self.stub.lines["77"] += [said(2, who=COLLEAGUE, content="when?"), said(3, who=OUTSIDER, content="me?")]
        self.poll()
        self.assertEqual([r["line"] for r in self.pending()], [3])


class CompanyAssignments(AssignBase):
    def test_a_colleagues_assignment_is_not_a_request_and_not_answered_as_blocked(self):
        self.stub = with_companies(AssignStub)
        self.stub.lines = {"77": []}
        self.cfg(participants={"company": True}, blocked={}, inbox={})
        self.poll()
        self.add(dict(todo(42, by=COLLEAGUE), updated_at=NEW))
        self.stub.readings = {"unreads": [note(10, "Assignment", thread=42, who=COLLEAGUE)], "reads": []}
        self.sync().behaviors["notifications"].run()
        self.assertEqual((self.pending(), self.stub.made("comments create")), ([], []))
        self.assertNotIn("request-42", self.todos())


class ProjectPeople(AssignBase):
    def setUp(self):
        super().setUp()
        self.cfg(assigned_todos={"scope": "account"}, project_people={str(OTHER): [GUEST]})

    def test_heard_in_their_project_only(self):
        self.add(todo(42, by=GUEST, bucket=OTHER))
        self.add(todo(43, by=GUEST))
        self.poll()
        self.assertEqual([(r["todo"], r["role"], r["project"]["id"]) for r in self.pending()], [(42, "participant", OTHER)])
        self.assertNotIn("request-43", self.todos())

    def test_malformed_config_refused(self):
        for bad in ([GUEST], {str(OTHER): GUEST}, {"x": [GUEST]}):
            self.cfg(project_people=bad)
            with self.assertRaises(ValueError):
                self.sync()


class ProjectPeopleHere(NotifBase):
    def test_listed_for_this_project_they_are_heard_here(self):
        self.cfg(project_people={str(PROJECT): [GUEST]})
        self.stub.lines["77"].append(line(2, who=GUEST, content="when?"))
        self.poll()
        self.assertEqual([(r["line"], r["role"]) for r in self.pending()], [(2, "participant")])


class ProjectPeoplePings(PingBase):
    def test_a_ping_is_no_project_so_they_are_not_heard_there(self):
        self.cfg(project_people={str(PROJECT): [GUEST]})
        self.stub.readings["unreads"] = [reading(people=(CAPTAIN, GUEST, ACTING))]
        self.poll()
        self.say(ping_line(2, who=GUEST, at=NEW), ping_line(3, at=NEW))
        self.poll()
        self.assertEqual([r["line"] for r in self.pending()], [3])


class Access(NotifBase):
    def test_lists_who_gets_through_and_where(self):
        self.stub = with_companies(NotifStub)
        self.cfg(operators=[COLLEAGUE], people=[CAPTAIN, OUTSIDER], project_people={str(OTHER): [GUEST]},
                 participants={"project": True, "company": True}, blocked={"reply": "Not me."})
        out = []
        self.sync().access(out=out.append)
        text = "\n".join(out)
        for want in (f"captain: person-{CAPTAIN} ({CAPTAIN}), always", f"person-{COLLEAGUE} ({COLLEAGUE})",
                     f"people (participants everywhere this home reads): person-{OUTSIDER} ({OUTSIDER})",
                     f"people in project {OTHER} only (participants there): person-{GUEST} ({GUEST})",
                     "anyone on the project who is not a client", f"anyone in company {COMPANY} (the captain's)",
                     "one automatic reply when they address the agent: 'Not me.'"):
            self.assertIn(want, text)

    def test_defaults_and_a_failed_name_read(self):
        self.stub.fail.add("/people/")
        out = []
        self.sync().access(out=out.append)
        self.assertIn(f"captain: person {CAPTAIN} ({CAPTAIN})", out[1])
        self.assertTrue(out[-2].endswith(": none"))
        self.assertIn('dropped with no reply ("blocked" is off)', out[-1])


class Config(NotifBase):
    def test_malformed_company_refused(self):
        for bad in ("yes", False, {"id": 1}):
            self.cfg(participants={"company": bad})
            with self.assertRaises(ValueError):
                self.sync()


class Init(unittest.TestCase):
    setUp, tearDown, init = test_init.InitTest.setUp, test_init.InitTest.tearDown, test_init.InitTest.init

    def test_participants_company_flag(self):
        self.assertEqual(self.init(participants_company=True).discover()[0]["participants"], {"company": True})
        self.assertNotIn("participants", self.init().discover()[0])


if __name__ == "__main__":
    unittest.main()
