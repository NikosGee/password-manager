"""Headless tests for the non-GUI modules (run from a temp directory)."""

import json
import os
import string
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Speed the KDF up for tests only (resolved at call time everywhere).
import crypto
crypto.KDF_ITERATIONS = 1000
import auth

from auth import (AuthManager, generate_recovery_code,
                  reset_password_with_recovery, setup_master,
                  verify_master_password, verify_recovery_code)
from backup import export_backup, import_backup
from generator import generate_password
from manager import PasswordManager
from strength import check_strength


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()


class TestAuth(TempDirTest):
    def test_setup_login_roundtrip(self):
        cipher, code = setup_master("nikos", "CorrectHorse!9")
        self.assertRegex(code, r"^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$")
        result, login_cipher = AuthManager().verify("nikos", "CorrectHorse!9")
        self.assertEqual(result, "success")
        self.assertEqual(login_cipher.decrypt(cipher.encrypt("hi")), "hi")

    def test_wrong_password_fails(self):
        setup_master("nikos", "CorrectHorse!9")
        result, cipher = AuthManager().verify("nikos", "wrong")
        self.assertEqual(result, "failed")
        self.assertIsNone(cipher)

    def test_no_plaintext_or_recovery_code_on_disk(self):
        _, code = setup_master("nikos", "CorrectHorse!9")
        raw = open("master.json").read()
        self.assertNotIn("CorrectHorse!9", raw)
        self.assertNotIn(code, raw)
        self.assertNotIn(code.replace("-", ""), raw)
        import hashlib
        self.assertNotIn(hashlib.sha256(b"CorrectHorse!9").hexdigest(), raw)

    def test_lockout_persists_across_restart(self):
        setup_master("nikos", "CorrectHorse!9")
        manager = AuthManager()
        for _ in range(auth.MAX_ATTEMPTS):
            manager.verify("nikos", "wrong")
        # a brand-new AuthManager (fresh app start) must still be locked
        fresh = AuthManager()
        self.assertTrue(fresh.is_locked_out())
        result, _ = fresh.verify("nikos", "CorrectHorse!9")
        self.assertEqual(result, "locked")

    def test_recovery_key_reset_keeps_vault_and_rotates(self):
        cipher, code = setup_master("nikos", "OldPass!1234")
        pm = PasswordManager(cipher)
        pm.add_password("site.com", "user", "sekret", "Other")

        # normalization: lowercase / no dashes / stray spaces all accepted
        messy = " " + code.lower().replace("-", " ") + " "
        self.assertTrue(verify_recovery_code(messy))

        new_cipher, new_code = reset_password_with_recovery(messy, "NewPass!5678")
        self.assertIsNotNone(new_cipher)
        self.assertNotEqual(new_code, code)

        result, login_cipher = AuthManager().verify("nikos", "NewPass!5678")
        self.assertEqual(result, "success")
        pm2 = PasswordManager(login_cipher)
        self.assertEqual(pm2.get_password("site.com")["password"], "sekret")

        # old key is retired, new one works
        self.assertFalse(verify_recovery_code(code))
        self.assertTrue(verify_recovery_code(new_code))

    def test_wrong_code_cannot_reset(self):
        setup_master("nikos", "OldPass!1234")
        bad = generate_recovery_code()
        cipher, new_code = reset_password_with_recovery(bad, "NewPass!5678")
        self.assertIsNone(cipher)
        self.assertIsNone(new_code)
        self.assertFalse(verify_recovery_code(bad))

    def test_rotate_recovery_key(self):
        cipher, code = setup_master("nikos", "CorrectHorse!9")
        new_code = auth.rotate_recovery_key(cipher.key)
        self.assertNotEqual(new_code, code)
        self.assertFalse(verify_recovery_code(code))
        self.assertTrue(verify_recovery_code(new_code))
        # the rotated key still unlocks the same vault
        rec_cipher, _ = reset_password_with_recovery(new_code, "NewPass!5678")
        self.assertEqual(rec_cipher.decrypt(cipher.encrypt("hi")), "hi")

    def test_verify_master_password(self):
        setup_master("nikos", "CorrectHorse!9")
        self.assertTrue(verify_master_password("CorrectHorse!9"))
        self.assertFalse(verify_master_password("nope"))


class TestManager(TempDirTest):
    def make_pm(self):
        cipher, _ = setup_master("nikos", "CorrectHorse!9")
        return PasswordManager(cipher)

    def test_add_get_delete_notes(self):
        pm = self.make_pm()
        pm.add_password("a.com", "user", "pw1", "Work", notes="my note")
        entry = pm.get_password("a.com")
        self.assertEqual(entry["password"], "pw1")
        self.assertEqual(entry["notes"], "my note")
        self.assertEqual(entry["category"], "Work")
        self.assertTrue(pm.delete_password("a.com"))
        self.assertIsNone(pm.get_password("a.com"))

    def test_vault_file_leaks_nothing(self):
        """The on-disk vault must not reveal entries OR metadata —
        no site names, usernames, notes, categories, or timestamps."""
        pm = self.make_pm()
        pm.add_password("mybank.com", "nikos_g007", "pw1", "Banking",
                        notes="my secret note")
        with open("vault.json", encoding="utf-8") as f:
            raw = f.read()
        for secret in ("mybank.com", "nikos_g007", "pw1",
                       "my secret note", "Banking", "updated_at"):
            self.assertNotIn(secret, raw)

    def test_history_only_on_change(self):
        pm = self.make_pm()
        pm.add_password("a.com", "user", "pw1", "Work")
        pm.add_password("a.com", "user2", "pw1", "Work")   # same password
        self.assertEqual(pm.get_history("a.com"), [])
        pm.add_password("a.com", "user2", "pw2", "Work")   # changed
        history = pm.get_history("a.com")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["password"], "pw1")

    def test_health_report_flags_weak_and_reused(self):
        pm = self.make_pm()
        pm.add_password("a.com", "u", "abc", "Work")            # weak
        pm.add_password("b.com", "u", "S4me!Pass#word88", "Work")  # reused
        pm.add_password("c.com", "u", "S4me!Pass#word88", "Work")  # reused
        pm.add_password("d.com", "u", generate_password(), "Work") # healthy
        report = {r["website"]: r["issues"] for r in pm.health_report()}
        self.assertIn("a.com", report)
        self.assertTrue(any("weak" in i for i in report["a.com"]))
        self.assertTrue(any("reused" in i for i in report["b.com"]))
        self.assertNotIn("d.com", report)

    def test_custom_categories(self):
        pm = self.make_pm()
        from manager import DEFAULT_CATEGORIES
        self.assertEqual(pm.get_categories(), DEFAULT_CATEGORIES)
        self.assertTrue(pm.add_category("Gaming"))
        self.assertFalse(pm.add_category("  gaming "))   # dupe (case/space)
        self.assertFalse(pm.add_category("   "))         # empty
        self.assertIn("Gaming", pm.get_categories())
        # persists (inside the encrypted blob) and never leaks to disk
        pm2 = PasswordManager(pm.cipher)
        self.assertIn("Gaming", pm2.get_categories())
        pm.add_password("g.com", "u", "x", "Gaming")
        self.assertEqual(pm.get_websites_by_category("Gaming"), ["g.com"])
        raw = open("vault.json", encoding="utf-8").read()
        self.assertNotIn("Gaming", raw)

    def test_delete_category(self):
        pm = self.make_pm()
        pm.add_category("Gaming")
        pm.add_password("g.com", "u", "x", "Gaming")
        pm.add_password("w.com", "u", "x", "Work")
        self.assertIsNone(pm.delete_category("Other"))      # protected
        self.assertIsNone(pm.delete_category("Nope"))       # unknown
        self.assertEqual(pm.delete_category("Gaming"), 1)   # 1 reassigned
        self.assertNotIn("Gaming", pm.get_categories())
        self.assertEqual(pm.get_password("g.com")["category"], "Other")
        self.assertEqual(pm.get_password("w.com")["category"], "Work")
        self.assertEqual(pm.delete_category("Social"), 0)   # defaults deletable

    def test_categories(self):
        pm = self.make_pm()
        pm.add_password("a.com", "u", "x", "Work")
        pm.add_password("b.com", "u", "x", "Banking")
        self.assertEqual(pm.get_websites_by_category("Work"), ["a.com"])
        self.assertEqual(sorted(pm.get_websites()), ["a.com", "b.com"])


class TestBackup(TempDirTest):
    def test_roundtrip_and_wrong_passphrase(self):
        cipher, _ = setup_master("nikos", "CorrectHorse!9")
        pm = PasswordManager(cipher)
        pm.add_password("a.com", "user", "pw1", "Work", notes="n")

        export_backup(pm.all_entries_decrypted(), "backup-pass", "vault.pmbackup")
        raw = open("vault.pmbackup").read()
        self.assertNotIn("pw1", raw)
        self.assertNotIn("a.com", raw)

        self.assertIsNone(import_backup("vault.pmbackup", "wrong"))
        entries = import_backup("vault.pmbackup", "backup-pass")
        self.assertEqual(entries["a.com"]["password"], "pw1")

        # restore into a fresh vault
        os.remove("vault.json")
        pm2 = PasswordManager(cipher)
        self.assertEqual(pm2.restore_entries(entries), 1)
        self.assertEqual(pm2.get_password("a.com")["password"], "pw1")
        self.assertEqual(pm2.get_password("a.com")["notes"], "n")


class TestGeneratorAndStrength(unittest.TestCase):
    def test_generator_classes_and_uniqueness(self):
        for _ in range(50):
            pw = generate_password(24)
            self.assertEqual(len(pw), 24)
            self.assertTrue(any(c in string.ascii_lowercase for c in pw))
            self.assertTrue(any(c in string.ascii_uppercase for c in pw))
            self.assertTrue(any(c in string.digits for c in pw))
            self.assertTrue(any(c in string.punctuation for c in pw))
        self.assertNotEqual(generate_password(), generate_password())
        with self.assertRaises(ValueError):
            generate_password(2)

    def test_recovery_code_format_and_uniqueness(self):
        codes = {generate_recovery_code() for _ in range(50)}
        self.assertEqual(len(codes), 50)
        for code in codes:
            self.assertRegex(code, r"^[A-HJ-KM-NP-Z2-9]{4}(-[A-HJ-KM-NP-Z2-9]{4}){3}$")

    def test_strength(self):
        self.assertEqual(check_strength(""), "weak")
        self.assertEqual(check_strength("abc"), "weak")
        self.assertEqual(check_strength("Password123!"), "medium")  # contains "password"
        self.assertEqual(check_strength("Tr!ckyM0use#42x"), "strong")
        self.assertEqual(check_strength("password123"), "weak")  # common-ish
        self.assertEqual(check_strength("aaaaaaaaaaaaaaaa"), "weak")
        self.assertEqual(check_strength(generate_password()), "strong")


if __name__ == "__main__":
    unittest.main(verbosity=2)
