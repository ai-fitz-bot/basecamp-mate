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
