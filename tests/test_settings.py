import os
import runpy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "strava" / "settings.py"


class DeploymentSettingsTests(TestCase):
    def _load_settings(self, environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(SETTINGS_PATH))

    def test_local_development_keeps_explicit_debug_fallback(self):
        loaded = self._load_settings({"CONTEXT": "DEBUG"})

        self.assertFalse(loaded["IS_VERCEL"])
        self.assertTrue(loaded["DEBUG"])
        self.assertIn("local-development-only", loaded["SECRET_KEY"])
        self.assertEqual(loaded["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"])

    def test_vercel_fails_closed_without_secret_key(self):
        with self.assertRaisesRegex(RuntimeError, "DJANGO_SECRET_KEY"):
            self._load_settings({"VERCEL": "1"})

    def test_vercel_disables_debug_and_allows_only_deployment_hosts(self):
        loaded = self._load_settings(
            {
                "ALLOWED_HOSTS": "routes.example.com,.internal.example.com",
                "CONTEXT": "DEBUG",
                "DJANGO_SECRET_KEY": "preview-secret-value-for-settings-test-only",
                "VERCEL": "1",
                "VERCEL_BRANCH_URL": "branch-preview.vercel.app",
                "VERCEL_PROJECT_PRODUCTION_URL": "production.vercel.app",
                "VERCEL_URL": "https://deployment.vercel.app/a-path-is-ignored",
            }
        )

        self.assertFalse(loaded["DEBUG"])
        self.assertNotIn(".vercel.app", loaded["ALLOWED_HOSTS"])
        self.assertEqual(
            loaded["ALLOWED_HOSTS"],
            [
                "deployment.vercel.app",
                "branch-preview.vercel.app",
                "production.vercel.app",
                "routes.example.com",
                ".internal.example.com",
            ],
        )
        self.assertEqual(loaded["DATA_UPLOAD_MAX_MEMORY_SIZE"], 1_048_576)
