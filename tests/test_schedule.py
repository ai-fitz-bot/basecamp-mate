"""Tests for when scheduled requests are done: the config's "schedule" (a new home: ask about a dated request, do a
repeating one on its due date), the answers remembered per list (`sync.py schedule set`, schedule.json), and the `when`
and `list` each scheduled request's record and note carry.

The basecamp CLI is stubbed; nothing touches the network.
"""
import io, json, os, sys, unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_assigned_todos import AssignBase, scheduled, todo  # noqa: E402
import behaviors  # noqa: E402
import sync  # noqa: E402
import test_init  # noqa: E402

LIST = 9  # the to-do list scheduled() puts a to-do in


class Timing(AssignBase):
    def setUp(self):
        super().setUp()
        self.cfg(schedule={"dated": "ask", "recurring": "due"})

    def request(self):
        [rec] = [r for r in self.pending() if r["kind"] == "todo-request"]
        return rec

    def test_a_dated_request_says_to_ask_until_its_list_has_an_answer(self):
        self.add(scheduled(42, rule=None))
        self.poll()
        rec = self.request()
        self.assertEqual((rec["when"], rec["list"]), ("ask", LIST))
        body = behaviors.inbox_note(rec, "1", "2")[1]
        self.assertIn("no one has said yet whether this list's dated to-dos are done on the due date or before it", body)
        self.assertIn(f"sync.py schedule set --list {LIST} --dated due|before", body)

    def test_the_answer_remembered_for_its_list_wins_then_the_remembered_default(self):
        self.sync().schedule_set("dated", "before", LIST)
        self.sync().schedule_set("dated", "due")
        self.add(scheduled(42, rule=None))
        self.add(scheduled(43, rule=None, parent=8))
        self.poll()
        recs = {r["todo"]: r for r in self.pending() if r["kind"] == "todo-request"}
        self.assertEqual((recs[42]["when"], recs[43]["when"]), ("before", "due"))
        self.assertIn("this list's dated to-dos are done before their due date", behaviors.inbox_note(recs[42], "1", "2")[1])

    def test_a_repeating_request_takes_the_recurring_default(self):
        self.add(scheduled(42))
        self.poll()
        rec = self.request()
        self.assertEqual(rec["when"], "due")
        self.assertIn("this list's repeating to-dos are done on their due date", behaviors.inbox_note(rec, "1", "2")[1])

    def test_an_undated_request_or_a_config_without_schedule_carries_nothing(self):
        self.add(todo(41))
        self.poll()
        self.assertNotIn("when", self.request())
        self.cfg(drop=("schedule",))
        self.add(scheduled(42, rule=None))
        self.poll()
        self.assertNotIn("when", [r for r in self.pending() if r.get("todo") == 42][0])

    def test_an_edit_carries_it_too_and_todo_show_prints_it(self):
        self.add(scheduled(42, rule=None))
        self.poll()
        self.edit(42, due_on="2026-11-30")
        self.poll()
        [upd] = [r for r in self.pending() if r["kind"] == "todo-request-update"]
        self.assertEqual(upd["when"], "ask")
        out = io.StringIO()
        with redirect_stdout(out):
            self.sync().todo_show("request-42")
        self.assertEqual(json.loads(out.getvalue())["when"], "ask")

    def test_schedule_set_validates_and_dry_run_saves_nothing(self):
        with self.assertRaises(ValueError):
            self.sync().schedule_set("dated", "later")
        self.sync(dry=True).schedule_set("dated", "due", LIST)
        self.assertFalse(os.path.exists(os.path.join(self.cfgdir, "schedule.json")))

    def test_malformed_config_refused(self):
        for bad in ({"dated": "soon"}, {"weekly": "due"}, "ask"):
            self.cfg(schedule=bad)
            with self.assertRaises(ValueError):
                self.sync()

    def test_cli(self):
        base = ["--home", self.home, "--config", os.path.join(self.cfgdir, "config.json")]
        self.assertEqual(sync.cli(["schedule", "set", *base, "--list", str(LIST), "--dated", "before",
                                   "--recurring", "ask"], runner=self.stub), 0)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(sync.cli(["schedule", "show", *base], runner=self.stub), 0)
        shown = json.loads(out.getvalue())
        self.assertEqual((shown["config"], shown["lists"]),
                         ({"dated": "ask", "recurring": "due"}, {str(LIST): {"dated": "before", "recurring": "ask"}}))


class Init(unittest.TestCase):
    setUp, tearDown, init = test_init.InitTest.setUp, test_init.InitTest.tearDown, test_init.InitTest.init

    def test_a_new_home_with_requests_gets_the_shipped_schedule_and_an_existing_one_keeps_its_own(self):
        self.assertEqual(self.init(assigned_todos=True).discover()[0]["schedule"], {"dated": "ask", "recurring": "due"})
        self.assertNotIn("schedule", self.init().discover()[0])
        self.init().main()  # an existing home without requests, then without a schedule
        self.assertNotIn("schedule", self.init(assigned_todos=True, force=True).discover()[0])


if __name__ == "__main__":
    unittest.main()
