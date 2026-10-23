"""Tests for blocked senders: someone the sync does not listen to never reaches the agent, and with "blocked" on gets one
short automatic reply where they addressed it (an @mention in a chat line or comment, a Ping line, an assignment).

Chats, comments, Pings, to-dos and notifications are stubbed; nothing touches the network.
"""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sync import ACTING, CAPTAIN, line  # noqa: E402
from test_notifications import NotifBase, PROJECT, note  # noqa: E402
from test_pings import CHAT, CIRCLE, PingBase, ping_line, reading  # noqa: E402
from test_assigned_todos import AssignBase, todo  # noqa: E402
import init_home  # noqa: E402
import test_init  # noqa: E402
import tools  # noqa: E402

STRANGER = 66666666
MENTION = f'<bc-attachment sgid="sgid-{ACTING}" content-type="application/vnd.basecamp.mention"></bc-attachment>'
NEW, OLD = "2099-01-01T00:00:00Z", "2000-01-01T00:00:00Z"


def said(id, who=STRANGER, content=MENTION + " can you fix the login?", at=NEW):
    return dict(line(id, who=who, content=content), created_at=at)


class Chats(NotifBase):
    def setUp(self):
        super().setUp()
        self.cfg(blocked={})
        self.poll()  # starts the clock: nothing from before it is answered
        self.stub.calls.clear()

    def blocked(self):
        return self.state("blocked.json")

    def test_a_stranger_mentioning_the_agent_in_a_relayed_chat_gets_one_reply_and_never_reaches_it(self):
        self.stub.lines["77"].append(said(2))
        self.poll()
        self.poll()
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.stub.chat_posts(), [("77", tools.BLOCKED_REPLY)])
        self.assertEqual(self.stub.posted(), [])  # no 👀
        self.assertEqual(list(self.blocked()["replied"]), [f"{STRANGER}:{PROJECT}:77"])
        self.assertIn(f"blocked person ({STRANGER}): chat line 2 in {PROJECT}/77 not relayed", self.log())

    def test_at_most_one_reply_per_person_and_chat_a_day(self):
        self.stub.lines["77"].append(said(2))
        self.poll()
        self.stub.lines["77"].append(said(3, content=MENTION + " hello?"))
        self.poll()
        self.assertEqual(len(self.stub.chat_posts()), 1)
        self.assertIn("(no reply: already answered today)", self.log())

    def test_a_strangers_line_that_does_not_address_the_agent_gets_nothing(self):
        self.stub.lines["77"].append(said(2, content="lunch?"))
        self.poll()
        self.assertEqual((self.pending(), self.stub.chat_posts()), ([], []))

    def test_a_mention_in_a_chat_nothing_relays_is_answered_there(self):
        self.stub.lines["78"] = [line(1), said(3)]
        self.notify(note(10, "Mention", thread=78, anchor=3, path="chats", who=STRANGER))
        self.poll()
        self.assertEqual(self.pending(), [])
        self.assertEqual([c for c, _ in self.stub.chat_posts()], ["78"])
        self.assertEqual(self.stub.marked, [["10"]])

    def test_a_comment_mention_is_answered_with_a_comment_on_that_thread(self):
        self.stub.comments["4"] = [{"id": 9, "creator": {"id": STRANGER, "name": "Sam"}, "content": MENTION + " look",
                                    "created_at": NEW, "parent": {"id": 4, "type": "Document", "title": "Roadmap"}}]
        self.notify(note(10, "Mention", thread=4, anchor=9, path="documents", who=STRANGER))
        self.poll()
        self.assertEqual(self.pending(), [])
        self.assertEqual([c[2] for c in self.stub.made("comments create")], ["4"])
        self.assertEqual(self.stub.inputs[-1], tools.BLOCKED_REPLY)
        self.assertIn("blocked Sam (", self.log())

    def test_custom_text_and_never_the_captain_the_agent_or_history(self):
        self.cfg(blocked={"reply": "Ask Caleb, please."})
        self.stub.lines["77"] += [said(2, at=OLD), said(3, who=ACTING), said(4, who=CAPTAIN, content=MENTION + " ok")]
        self.poll()
        self.assertEqual(self.stub.chat_posts(), [])
        self.assertIn("(no reply: from before automatic replies started)", self.log())
        self.assertEqual([r["line"] for r in self.pending()], [4])  # the captain's line is relayed as ever
        self.stub.lines["77"].append(said(5))
        self.poll()
        self.assertEqual(self.stub.chat_posts(), [("77", "Ask Caleb, please.")])

    def test_dry_run_posts_and_saves_nothing(self):
        self.stub.lines["77"].append(said(2))
        self.poll(dry=True)
        self.assertEqual(self.stub.chat_posts(), [])
        self.assertNotIn("replied", self.blocked())
        self.assertIn("would post the automatic reply", self.log())

    def test_a_failed_reply_is_logged_not_retried_and_not_a_failed_read(self):
        self.stub.lines["77"].append(said(2))
        self.stub.fail_post = True
        self.notify(note(10, "Chat", thread=77, path="chats", section="chats"))
        self.poll()
        self.assertIn("the automatic reply failed, not retried", self.log())
        self.assertEqual(self.stub.marked, [["10"]])  # the chat's read still counts as handled
        self.stub.fail_post = False
        self.poll()
        self.assertEqual(len(self.stub.chat_posts()), 1)  # the failed attempt only

    def test_off_a_stranger_is_dropped_with_a_log_line_and_nothing_posted(self):
        self.cfg(drop=("blocked",))
        self.stub.lines["77"].append(said(2))
        self.poll()
        self.assertEqual((self.pending(), self.stub.chat_posts()), ([], []))
        self.assertIn('(no automatic reply: "blocked" is off)', self.log())

    def test_without_a_profile_nothing_is_posted(self):
        self.cfg(drop=("profile",))
        self.stub.lines["77"].append(said(2))
        self.poll()
        self.assertEqual(self.stub.chat_posts(), [])

    def test_malformed_config_refused(self):
        for bad in ("yes", {"text": "x"}, {"reply": 3}):
            self.cfg(blocked=bad)
            with self.assertRaises(ValueError):
                self.sync()


class Pings(PingBase):
    def setUp(self):
        super().setUp()
        self.cfg(pings={}, blocked={})
        self.poll()
        self.stub.calls.clear()

    def test_a_ping_from_a_stranger_is_answered_in_the_ping(self):
        self.stub.readings["unreads"] = [reading(people=(STRANGER, ACTING))]
        self.say(ping_line(2, who=STRANGER, at=NEW))
        self.poll()
        self.poll()
        self.assertEqual(self.pending(), [])
        self.assertEqual([p for p in self.stub.paths("post") if "/chats/" in p], [f"/buckets/{CIRCLE}/chats/{CHAT}/lines.json"])

    def test_without_blocked_a_strangers_ping_is_never_read(self):
        self.cfg(drop=("blocked",))
        self.stub.readings["unreads"] = [reading(people=(STRANGER, ACTING))]
        self.say(ping_line(2, who=STRANGER, at=NEW))
        self.poll()
        self.assertFalse(any(f"/buckets/{CIRCLE}/" in p for p in self.stub.paths()))


class Assignments(AssignBase):
    def setUp(self):
        super().setUp()
        self.cfg(inbox={}, blocked={})
        self.poll()
        self.stub.calls.clear()

    def notify(self, *items):
        self.stub.readings = {"unreads": list(items), "reads": []}
        self.sync().behaviors["notifications"].run()

    def test_a_todo_a_stranger_assigns_is_answered_on_the_todo_and_never_a_request(self):
        self.add(dict(todo(42, by=STRANGER), updated_at=NEW))
        self.notify(note(10, "Assignment", thread=42, who=STRANGER))
        self.assertEqual((self.pending(), self.stub.notes), ([], []))
        self.assertEqual([c[2] for c in self.stub.made("comments create")], ["42"])

    def test_the_sweep_never_answers_since_it_only_guesses_who_assigned(self):
        self.add(dict(todo(43, by=STRANGER), updated_at=NEW))
        self.sync().behaviors["assigned-todos"].run()
        self.assertEqual(self.stub.made("comments create"), [])


class Init(unittest.TestCase):
    """init: a new home answers blocked senders; --no-blocked-reply leaves it off; a re-run keeps an existing setting."""
    setUp, tearDown, init = test_init.InitTest.setUp, test_init.InitTest.tearDown, test_init.InitTest.init

    def test_new_home_custom_text_and_off(self):
        self.assertEqual(self.init().discover()[0]["blocked"], {})
        self.assertEqual(self.init(blocked="Not me.").discover()[0]["blocked"], {"reply": "Not me."})
        self.assertNotIn("blocked", self.init(blocked=False).discover()[0])

    def test_an_existing_config_without_it_keeps_running_unchanged(self):
        self.init(blocked=False).main()
        self.init().main()  # no --force needed: nothing differs
        self.assertNotIn("blocked", json.load(open(os.path.join(self.dir, "config.json"))))

    def test_flags(self):
        self.assertEqual(init_home.cli(["https://app.basecamp.com/1/projects/2", "--login", "x", "--home", self.home,
                                        "--blocked-reply", "a", "--no-blocked-reply"]), 2)


if __name__ == "__main__":
    unittest.main()
