"""Tests for the session alert: one chat line to the owner while the firstmate session is down and inbox notes wait.

The firstmate home is a temp dir with a fake state/.lock and state/inbox; the basecamp CLI is stubbed.
"""
import json, os, sys, time, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_sync import Base, Stub  # noqa: E402
import tools  # noqa: E402

CHAT = "55"


class SessionAlert(Base):
    def setUp(self):
        super().setUp()
        self.stub = Stub()
        self.cfg(profile="agent", inbox={}, session_alert={"chat": CHAT, "after_minutes": 10})
        os.makedirs(os.path.join(self.home, "state", "inbox", "handled"))

    def cfg(self, **kw):
        p = os.path.join(self.cfgdir, "config.json")
        cfg = json.load(open(p))
        cfg.update(kw)
        json.dump(cfg, open(p, "w"))

    def lock(self, pid, at=None):
        p = os.path.join(self.home, "state", ".lock")
        open(p, "w").write(f"{pid}\n")
        if at is not None:
            os.utime(p, (at, at))

    def note(self, age, handled=False):
        at = int(time.time() - age)
        d = os.path.join(self.home, "state", "inbox", *(["handled"] if handled else []))
        open(os.path.join(d, f"{at}-abc{len(os.listdir(d))}.note"), "w").write("id=x\n")

    def step(self, dry=False):
        self.sync(dry=dry).behaviors["session-alert"].run()

    def state(self):
        p = os.path.join(self.cfgdir, "session-alert.json")
        return json.load(open(p)) if os.path.exists(p) else {}

    def log(self):
        p = os.path.join(self.cfgdir, "sync.log")
        return open(p).read() if os.path.exists(p) else ""

    def test_down_with_an_old_note_posts_once_mentioning_the_owner(self):
        self.note(age=3600)
        self.note(age=30)
        self.step()
        self.step()
        posts = self.stub.chat_posts()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][0], CHAT)
        self.assertIn("sgid-owner", posts[0][1])
        self.assertIn("2 Basecamp messages have been waiting", posts[0][1])
        self.assertTrue(self.state()["alerted"])
        self.assertIn("session alert: posted line", self.log())

    def test_a_stale_pid_counts_as_down(self):
        self.lock(2 ** 22 + 12345)  # above any pid_max default: no such process
        self.note(age=3600)
        self.step()
        self.assertEqual(len(self.stub.chat_posts()), 1)

    def test_a_lock_written_before_this_boot_is_down_even_when_its_pid_lives(self):
        boot = tools.boot_time() or int(time.time()) - 100
        self.lock(os.getpid(), at=boot - 60)
        self.note(age=3600)
        with mock.patch.object(tools, "boot_time", return_value=boot):
            self.step()
        self.assertEqual(len(self.stub.chat_posts()), 1)

    def test_a_live_holder_posts_nothing_and_clears_an_alert(self):
        self.note(age=3600)
        self.step()
        self.lock(os.getpid())
        self.step()
        self.assertEqual(self.state(), {})
        self.assertIn("session alert cleared", self.log())
        os.remove(os.path.join(self.home, "state", ".lock"))
        self.step()  # down again: a new alert
        self.assertEqual(len(self.stub.chat_posts()), 2)

    def test_young_or_handled_notes_post_nothing(self):
        self.note(age=60)
        self.note(age=3600, handled=True)
        self.step()
        self.assertEqual((self.stub.chat_posts(), self.state()), ([], {}))

    def test_no_notes_posts_nothing(self):
        self.step()
        self.assertEqual(self.stub.chat_posts(), [])

    def test_dry_run_only_logs(self):
        self.note(age=3600)
        self.step(dry=True)
        self.assertEqual((self.stub.chat_posts(), self.state()), ([], {}))
        self.assertIn("dry session alert", self.log())

    def test_a_failed_post_is_logged_and_retried(self):
        self.note(age=3600)
        self.stub.fail_post = True
        self.step()
        self.assertIn("FAILED session alert", self.log())
        self.assertEqual(self.state(), {})
        self.stub.fail_post = False
        self.step()
        self.assertTrue(self.state()["alerted"])

    def test_the_owner_profile_never_posts(self):
        self.stub.me = 33333333  # the captain
        self.note(age=3600)
        self.step()
        self.step()
        self.assertEqual(self.stub.chat_posts(), [])
        self.assertTrue(self.state()["refused"])

    def test_watches_another_fm_home(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(os.path.join(other, "state", "inbox"))
        open(os.path.join(other, "state", "inbox", f"{int(time.time()) - 3600}-x.note"), "w").write("")
        self.lock(os.getpid())  # this home is up; the watched one is not
        self.cfg(inbox={"fm_home": other})
        self.step()
        self.assertEqual(len(self.stub.chat_posts()), 1)

    def test_config_errors(self):
        for bad in ({"after_minutes": 5}, {"chat": 1, "every": 3}, {"chat": 1, "after_minutes": -1}, "yes"):
            self.cfg(session_alert=bad)
            with self.assertRaises(ValueError):
                self.sync()
        self.cfg(session_alert={"chat": 1}, inbox=None)
        with self.assertRaises(ValueError):
            self.sync()

    def test_off_by_default(self):
        self.cfg(session_alert=None)
        self.assertFalse(self.sync().behaviors["session-alert"].on)
        self.note(age=3600)
        self.sync().main([])
        self.assertEqual(self.stub.chat_posts(), [])


if __name__ == "__main__":
    unittest.main()
