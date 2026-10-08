import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scripts import production_preflight as preflight

ROOT = Path(__file__).resolve().parents[1]


class HostingerDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
        self.services = self.compose["services"]

    def test_services_bind_only_to_loopback(self):
        self.assertNotIn("caddy", self.services)
        self.assertEqual(["127.0.0.1:3337:8000"], self.services["api"]["ports"])
        self.assertEqual(["127.0.0.1:3336:3000"], self.services["web"]["ports"])
        self.assertNotIn("ports", self.services["maintenance"])

    def test_host_nginx_routes_public_traffic_to_loopback_services(self):
        nginx = (ROOT / "deploy/hostinger/nginx.triven-cinema.conf").read_text()
        self.assertIn("server_name cinema.devansh.info;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:3336;", nginx)
        self.assertIn("proxy_pass http://127.0.0.1:3337;", nginx)
        self.assertNotIn("proxy_pass http://api:8000;", nginx)
        self.assertNotIn("$proxy_add_x_forwarded_for", nginx)
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", nginx)

    def test_alternative_host_caddy_routes_to_the_same_loopback_services(self):
        caddy = (ROOT / "deploy/hostinger/Caddyfile").read_text()
        self.assertIn("cinema.devansh.info {", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:3336", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:3337", caddy)
        self.assertNotIn("reverse_proxy api:8000", caddy)

    def test_maintenance_does_not_inherit_the_api_http_healthcheck(self):
        self.assertTrue(self.services["maintenance"]["healthcheck"]["disable"])
        for name in ("api", "web"):
            self.assertIn("test", self.services[name]["healthcheck"])

    def test_api_and_maintenance_share_persistent_storage(self):
        self.assertIn("./storage:/app/storage", self.services["api"]["volumes"])
        self.assertIn("./storage:/app/storage", self.services["maintenance"]["volumes"])

    def test_production_template_protects_paid_render_path(self):
        text = (ROOT / ".env.production.example").read_text()
        self.assertIn('APP_ENV="production"', text)
        self.assertIn('VIDEO_PROVIDER="modal"', text)
        self.assertIn("ENABLE_SYNC_RENDER_ENDPOINTS=false", text)
        self.assertIn("JOB_WORKERS=1", text)
        self.assertIn("JOB_MAX_PENDING=3", text)
        self.assertIn("MAX_1080P_SCENE_SECONDS=30", text)
        self.assertIn("MAX_4K_SCENE_SECONDS=15", text)

    def test_production_domain_and_auth_defaults(self):
        env_text = (ROOT / ".env.production.example").read_text()
        nginx_text = (ROOT / "deploy/hostinger/nginx.triven-cinema.conf").read_text()
        self.assertIn('TRIVEN_DOMAIN="cinema.devansh.info"', env_text)
        self.assertIn('FRONTEND_URL="https://cinema.devansh.info"', env_text)
        self.assertIn('AUTO_LOGIN_EMAIL=""', env_text)
        self.assertIn("AUTH_ENABLED=true", env_text)
        self.assertIn("DEMO_AUTH_SHOW_OTP=false", env_text)
        self.assertIn("server_name cinema.devansh.info;", nginx_text)


class ProductionPreflightTests(unittest.TestCase):
    def setUp(self):
        preflight.ERRORS.clear()
        preflight.WARNINGS.clear()
        self.env = {
            "TRIVEN_DOMAIN": "cinema.devansh.info",
            "FRONTEND_URL": "https://cinema.devansh.info",
            "APP_ENV": "production",
            "DEBUG": "false",
            "AUTH_ENABLED": "true",
            "AUTO_LOGIN_EMAIL": "",
            "DEMO_AUTH_SHOW_OTP": "false",
            "ENABLE_SYNC_RENDER_ENDPOINTS": "false",
            "TRIVEN_SECRET_KEY": "s" * 48,
            "SMTP_HOST": "smtp.example.test",
            "SMTP_FROM": "noreply@cinema.devansh.info",
            "SMTP_SECURITY": "starttls",
        }

    def validate(self, **changes):
        preflight.ERRORS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            preflight.validate_production_settings({**self.env, **changes})
        return preflight.ERRORS

    def test_secure_production_configuration_passes(self):
        self.assertEqual([], self.validate())

    def test_unsafe_runtime_defaults_must_be_explicitly_disabled(self):
        for key in ("DEMO_AUTH_SHOW_OTP", "ENABLE_SYNC_RENDER_ENDPOINTS"):
            with self.subTest(key=key):
                value = self.env.pop(key)
                self.assertTrue(any(key in error for error in self.validate()))
                self.env[key] = value

    def test_unsafe_public_settings_are_errors(self):
        cases = {
            "TRIVEN_DOMAIN": "devansh.info",
            "FRONTEND_URL": "http://cinema.devansh.info",
            "APP_ENV": "development",
            "DEBUG": "true",
            "AUTH_ENABLED": "false",
            "AUTO_LOGIN_EMAIL": "shared@example.test",
            "DEMO_AUTH_SHOW_OTP": "true",
            "TRIVEN_SECRET_KEY": "short",
            "SMTP_HOST": "",
            "SMTP_FROM": "",
            "SMTP_SECURITY": "none",
            "CORS_ORIGINS": '["*"]',
            "ENABLE_SYNC_RENDER_ENDPOINTS": "true",
            "JOB_WORKERS": "2",
            "BILLING_ENFORCE_CREDITS": "true",
        }
        for key, value in cases.items():
            with self.subTest(key=key):
                errors = self.validate(**{key: value})
                self.assertTrue(any(key in error for error in errors), errors)

    def test_compose_resolved_environment_is_used_without_logging_secrets(self):
        payload = {"services": {"api": {"environment": self.env}}}
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        output = io.StringIO()
        with mock.patch.object(preflight.shutil, "which", return_value="docker"), \
             mock.patch.object(preflight, "command_ok", return_value=True), \
             mock.patch.object(preflight.subprocess, "run", return_value=completed), \
             contextlib.redirect_stdout(output):
            self.assertEqual(self.env, preflight.resolved_compose_environment())
        self.assertNotIn(self.env["TRIVEN_SECRET_KEY"], output.getvalue())

    def test_compose_failure_does_not_print_potentially_sensitive_stderr(self):
        completed = subprocess.CompletedProcess([], 1, "", "secret-from-env")
        output = io.StringIO()
        with mock.patch.object(preflight.shutil, "which", return_value="docker"), \
             mock.patch.object(preflight, "command_ok", return_value=True), \
             mock.patch.object(preflight.subprocess, "run", return_value=completed), \
             contextlib.redirect_stdout(output):
            self.assertIsNone(preflight.resolved_compose_environment())
        self.assertTrue(preflight.ERRORS)
        self.assertNotIn("secret-from-env", output.getvalue())


class DeploymentScriptTests(unittest.TestCase):
    """Exercise launch gates with fake Docker/curl commands; never touch a daemon."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "bin").mkdir()
        (self.root / ".env").write_text("# fixture\n")
        for script in ("deploy_hostinger.sh", "status_hostinger.sh"):
            shutil.copy2(ROOT / "scripts" / script, self.root / "scripts" / script)
        self.write_command("python3", '#!/bin/sh\nexit 0\n')
        self.write_command("docker", '''#!/bin/sh
printf 'docker %s\\n' "$*" >> "$COMMAND_LOG"
case "$*" in
  *" run "*) [ "${FAIL_BACKUP:-}" != 1 ] || exit 1 ;;
  *" up "*) [ "${FAIL_STARTUP:-}" != 1 ] || exit 1 ;;
esac
exit 0
''')
        self.write_command("curl", '''#!/bin/sh
printf 'curl %s\\n' "$*" >> "$COMMAND_LOG"
if [ -n "${FAIL_URL:-}" ]; then
  for argument in "$@"; do
    [ "$argument" != "$FAIL_URL" ] || exit 22
  done
fi
exit 0
''')
        self.write_command("systemctl", '#!/bin/sh\nexit 0\n')

    def write_command(self, name, body):
        path = self.root / "bin" / name
        path.write_text(body)
        path.chmod(0o755)

    def run_script(self, name="deploy_hostinger.sh", args=(), **settings):
        env = {**os.environ, "PATH": f"{self.root / 'bin'}:{os.environ['PATH']}",
               "COMMAND_LOG": str(self.root / "commands.log"), **settings}
        result = subprocess.run(
            ["bash", str(self.root / "scripts" / name), *args],
            env=env, capture_output=True, text=True, timeout=10,
        )
        log = self.root / "commands.log"
        return result, log.read_text() if log.exists() else ""

    def test_success_requires_both_services_locally_and_over_https(self):
        result, commands = self.run_script()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("up -d --remove-orphans --wait --wait-timeout 300", commands)
        self.assertIn("http://127.0.0.1:3336/", commands)
        self.assertIn("http://127.0.0.1:3337/api/v1/health/ready", commands)
        self.assertIn("https://cinema.devansh.info/api/v1/health/ready", commands)
        self.assertIn("https://cinema.devansh.info/\n", commands)

    def test_backup_failure_aborts_before_replacing_services(self):
        result, commands = self.run_script(FAIL_BACKUP="1")
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn(" up ", commands)

    def test_frontend_startup_failure_aborts_before_public_checks(self):
        result, commands = self.run_script(FAIL_STARTUP="1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("logs --tail=160 api web maintenance", commands)
        self.assertNotIn("curl ", commands)

    def test_public_frontend_failure_fails_deployment(self):
        result, _ = self.run_script(FAIL_URL="https://cinema.devansh.info/")
        self.assertNotEqual(0, result.returncode)

    def test_explicit_bootstrap_flag_skips_only_public_checks(self):
        result, commands = self.run_script(args=("--skip-public-check",))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("http://127.0.0.1:3336/", commands)
        self.assertNotIn("https://", commands)

    def test_bootstrap_still_rejects_unhealthy_local_frontend(self):
        result, _ = self.run_script(args=("--skip-public-check",), FAIL_URL="http://127.0.0.1:3336/")
        self.assertNotEqual(0, result.returncode)

    def test_status_returns_nonzero_when_public_frontend_is_unhealthy(self):
        result, _ = self.run_script(name="status_hostinger.sh", FAIL_URL="https://cinema.devansh.info/")
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
