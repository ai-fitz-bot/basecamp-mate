"""Tests for decisions anywhere: `todo create` in any project of the account (--project, or "todos": {"project"}), in any
list, or as a card in any card table column, with everything later on it (comments, notifications, completion) in its
project.

The basecamp CLI and the notifications are stubbed; nothing touches the network.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sync import CAPTAIN  # noqa: E402
from test_tools import comment  # noqa: E402
from test_notifications import PROJECT, note  # noqa: E402
from test_assigned_todos import OTHER, AssignBase  # noqa: E402
import sync  # noqa: E402


class Anywhere(AssignBase):
    def setUp(self):
        super().setUp()
        self.cfg(assigned_todos=False, todos={"todoset": "66"})

    def made(self, verb):
        """The (arguments, project) of each `verb` call, e.g. "todos create"."""
        return [(c, p) for c, p in self.stub.on if c[:2] == verb.split()]

    def test_the_default_is_this_projects_todo_set_as_before(self):
        self.create()
        [(args, project)] = self.made("todos create")
        self.assertEqual((args[3:6], project), (["--loose", "--todoset", "66"], str(PROJECT)))
        self.assertNotIn("bucket", self.todos()["ta-x"])

    def test_another_project_takes_its_own_todo_set_and_keeps_the_project(self):
        tid = self.create(project=str(OTHER))
        [(args, project)] = self.made("todos create")
        self.assertEqual((args[3:4], project), (["--loose"], str(OTHER)))  # the configured to-do set is this project's
        self.assertEqual(self.todos()["ta-x"]["bucket"], OTHER)
        self.assertTrue(self.sync().todo_comment("ta-x", "Ready."))
        self.assertTrue(self.sync().todo_complete("ta-x"))
        self.assertEqual([p for _, p in self.made("comments create") + self.made("todos complete")], [str(OTHER)] * 2)
        self.assertEqual(self.todos()["ta-x"]["todo"], tid)

    def test_the_config_can_name_another_project_and_list(self):
        self.cfg(todos={"project": OTHER, "list": "55"})
        self.create()
        self.create(key="here", project=str(PROJECT))
        (first, p1), (second, p2) = self.made("todos create")
        self.assertEqual((first[3:5], p1), (["--list", "55"], str(OTHER)))
        self.assertEqual((second[3:4], p2), (["--loose"], str(PROJECT)))  # the list is the other project's

    def test_subtasks_go_to_its_project(self):
        self.create(project=str(OTHER), subtasks=["Merge?", "Release?"])
        self.assertEqual([p for _, p in self.made("subtasks create")], [str(OTHER)] * 2)

    def test_a_card_in_any_column_completed_by_moving_it_to_done(self):
        cid = self.create(project=str(OTHER), card=("300", "301"))
        [(args, project)] = self.made("cards create")
        self.assertEqual((args[4:8], args[-2:], project),
                         (["--card-table", "300", "--column", "301"], ["--assignee", str(CAPTAIN)], str(OTHER)))
        rec = self.todos()["ta-x"]
        self.assertEqual((rec["todo"], rec["type"], rec["bucket"]), (cid, "card", OTHER))
        self.assertTrue(self.sync().todo_complete("ta-x"))
        self.assertEqual([(c[2], p) for c, p in self.made("cards done")], [(str(cid), str(OTHER))])

    def test_a_card_takes_no_subtasks_list_or_due_date(self):
        for kw in ({"subtasks": ["a?", "b?"]}, {"todolist": "5"}, {"due": "2099-01-01"}):
            with self.assertRaises(ValueError):
                self.create(card=("300", "301"), **kw)

    def test_track_in_another_project(self):
        self.stub.comments["70"] = [comment(3)]
        self.assertTrue(self.sync().todo_track("old", 70, project=str(OTHER)))
        self.assertEqual(self.todos()["old"]["bucket"], OTHER)
        self.assertEqual([p for _, p in self.made("comments list")], [str(OTHER)])

    def test_cli_flags(self):
        with open(os.path.join(self.tmp, "b.md"), "w") as f:
            f.write("Evidence.")
        base = ["--home", self.home, "--config", os.path.join(self.cfgdir, "config.json")]
        self.assertEqual(sync.cli(["todo", "create", *base, "--key", "k", "--title", "Merge?", "--body-file",
                                   os.path.join(self.tmp, "b.md"), "--project", str(OTHER), "--card-table", "300",
                                   "--column", "301"], runner=self.stub), 0)
        self.assertEqual(self.todos()["k"]["type"], "card")
        with self.assertRaises(SystemExit):
            sync.cli(["todo", "create", *base, "--key", "j", "--title", "Merge?", "--card-table", "300"], runner=self.stub)

    def test_malformed_config_refused(self):
        self.cfg(todos={"where": "x"})
        with self.assertRaises(ValueError):
            self.sync()


class Notified(AssignBase):
    """Notifications in another project are this home's for the decisions it put there."""

    def setUp(self):
        super().setUp()
        self.cfg(assigned_todos=False, todos={}, inbox={})
        self.poll()
        self.stub.calls.clear()

    def notify(self, *items):
        self.stub.readings = {"unreads": list(items), "reads": []}
        self.sync().behaviors["notifications"].run()

    def test_a_comment_on_a_decision_in_another_project_is_relayed(self):
        tid = self.create(project=str(OTHER))
        self.stub.comments[str(tid)] = [comment(9)]
        self.notify(note(10, thread=tid, anchor=9, bucket=OTHER))
        [rec] = self.pending()
        self.assertEqual((rec["kind"], rec["key"], rec["comment"]), ("todo-comment", "ta-x", 9))
        self.assertEqual(self.stub.marked, [["10"]])

    def test_its_completion_is_handled_and_marked_and_others_left_alone(self):
        tid = self.create(project=str(OTHER))
        self.notify(note(10, "Completion", thread=tid, bucket=OTHER), note(11, "Completion", thread=tid + 1, bucket=OTHER))
        self.assertEqual((self.pending(), self.stub.marked), ([], [["10"]]))

    def test_a_decision_cards_own_event_is_not_unmonitored(self):
        cid = self.create(card=("300", "301"))
        self.notify(note(10, "Event", thread=cid, path="cards"))
        self.assertEqual((self.pending(), self.stub.marked), ([], [["10"]]))
        self.assertFalse(os.path.exists(os.path.join(self.cfgdir, "unmonitored.json")))


if __name__ == "__main__":
    unittest.main()
