"""Exercise shell guards with a fake CLI; never contact GCP or build images."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_cloud(tmp_path):
    log = tmp_path / 'commands.jsonl'
    cli = tmp_path / 'gcloud'
    cli.write_text(
        f'#!{sys.executable}\n'
        'import json, os, sys\n'
        'from pathlib import Path\n'
        "with Path(os.environ['CLI_LOG']).open('a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:4] == ['run', 'jobs', 'replace']: Path(os.environ['JOB_SPEC']).write_text(Path(sys.argv[4]).read_text())\n"
        "if os.environ.get('FAIL_CLI') == 'true': sys.exit(1)\n"
        "if sys.argv[1:4] == ['sql', 'instances', 'describe']: print(os.environ.get('SQL_STATE', 'RUNNABLE'))\n"
        "if sys.argv[1:4] == ['secrets', 'versions', 'describe']: print(os.environ.get('SECRET_STATE', 'ENABLED'))\n"
        "if sys.argv[1:4] == ['run', 'jobs', 'execute'] and os.environ.get('FAIL_JOB') == 'true': sys.exit(1)\n"
    )
    cli.chmod(0o755)
    (tmp_path / 'python').symlink_to(sys.executable)
    env = {
        **os.environ,
        'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
        'CLI_LOG': str(log),
        'JOB_SPEC': str(tmp_path / 'job-spec.json'),
        'SERVICE_ACCOUNT': 'test-runtime@test-project.iam.gserviceaccount.com',
        'GCP_PROJECT_ID': 'test-project',
        'GCP_REGION': 'us-central1',
        'REGION': 'us-central1',
        'CLOUD_SQL_INSTANCE': 'test-project:us-central1:portal-db',
        'IMAGE': 'example/api@sha256:' + 'a' * 64,
    }
    return env, log


def run_script(name, env):
    return subprocess.run(['bash', str(ROOT / 'deploy' / name)], env=env, capture_output=True, text=True, check=False)


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


@pytest.mark.parametrize('missing', ['CLOUD_SQL_INSTANCE'])
def test_missing_config_stops_before_any_cloud_command(fake_cloud, missing):
    env, log = fake_cloud
    env[missing] = ''
    assert run_script('check-cloud-sql-ready.sh', env).returncode != 0
    assert not calls(log)


def test_preflight_checks_only_metadata(fake_cloud):
    env, log = fake_cloud
    assert run_script('check-cloud-sql-ready.sh', env).returncode == 0
    commands = calls(log)
    assert len(commands) == 9
    assert commands[0][:3] == ['sql', 'instances', 'describe']
    assert all(command[:3] == ['secrets', 'versions', 'describe'] for command in commands[1:])
    assert not any('access' in command or 'enable' in command for command in commands)


@pytest.mark.parametrize('settings', [{'SQL_STATE': 'STOPPED'}, {'SECRET_STATE': 'DISABLED'}, {'FAIL_CLI': 'true'}])
def test_unready_resource_or_api_failure_blocks_release(fake_cloud, settings):
    env, log = fake_cloud
    env.update(settings)
    assert run_script('check-cloud-sql-ready.sh', env).returncode != 0
    assert all(command[0] in {'sql', 'secrets'} for command in calls(log))


def test_mutable_migration_image_is_rejected_before_cloud_access(fake_cloud):
    env, log = fake_cloud
    env['IMAGE'] = 'example/api:latest'
    assert run_script('migrate-cloud-run-job.sh', env).returncode != 0
    assert not calls(log)


def test_schema_job_uses_digest_and_waits_for_completion(fake_cloud):
    env, log = fake_cloud
    assert run_script('migrate-cloud-run-job.sh', env).returncode == 0
    deploy, execute = calls(log)
    assert deploy[:3] == ['run', 'jobs', 'replace']
    spec = json.loads(Path(env['JOB_SPEC']).read_text())
    task = spec['spec']['template']['spec']['template']['spec']
    assert task['containers'][0]['image'] == env['IMAGE']
    assert env['CLOUD_SQL_INSTANCE'] in task['containers'][1]['args']
    assert '--private-ip' in task['containers'][1]['args']
    assert execute[:3] == ['run', 'jobs', 'execute'] and '--wait' in execute


def test_failed_schema_job_fails_the_release_step(fake_cloud):
    env, log = fake_cloud
    env['FAIL_JOB'] = 'true'
    assert run_script('migrate-cloud-run-job.sh', env).returncode != 0
    assert all(command[:2] == ['run', 'jobs'] for command in calls(log))


def test_preflight_uses_portal_secret_ids_by_default(fake_cloud):
    env, log = fake_cloud
    assert run_script('check-cloud-sql-ready.sh', env).returncode == 0
    secret_ids = [arg for command in calls(log) for arg in command if arg.startswith('--secret=')]
    assert secret_ids == [
        '--secret=EXTRACTION_PORTAL_DATABASE_URL',
        '--secret=EXTRACTION_PORTAL_FLASK_SECRET_KEY',
        '--secret=EXTRACTION_PORTAL_FERNET_KEY',
        '--secret=MSGRAPH_CLIENT_SECRET',
        '--secret=MSGRAPH_CLIENT_ID',
        '--secret=PLAID_SECRET',
        '--secret=PLAID_CLIENT_ID',
        '--secret=PLAID_ENV',
    ]


def test_job_mounts_secrets_without_aliases(fake_cloud):
    env, _log = fake_cloud
    assert run_script('migrate-cloud-run-job.sh', env).returncode == 0
    spec = json.loads(Path(env['JOB_SPEC']).read_text())
    task = spec['spec']['template']['spec']['template']['spec']
    secret_env = [value for value in task['containers'][0]['env'] if 'valueFrom' in value]
    assert len(secret_env) == 3
    for value in secret_env:
        assert value['valueFrom']['secretKeyRef'] == {'name': value['name'], 'key': 'latest'}
