"""Render a private Cloud Run Job; JSON is accepted as YAML by gcloud."""

import json
import os


def job_spec(name, image, instance, service_account):
    secrets = ['EXTRACTION_PORTAL_FLASK_SECRET_KEY', 'EXTRACTION_PORTAL_FERNET_KEY', 'EXTRACTION_PORTAL_DATABASE_URL']
    env = {
        'FLASK_APP': 'src.api.app:create_app',
        'FLASK_ENV': 'production',
        'USE_GCP_SECRETS': 'true',
        'GCP_PROJECT_ID': os.environ['GCP_PROJECT_ID'],
        'ENABLE_DEV_LOGIN': 'false',
        'SESSION_COOKIE_SECURE': 'true',
        'SESSION_COOKIE_NAME': '__session',
        'SESSION_BACKEND': 'sqlalchemy',
        'RATELIMIT_STORAGE_BACKEND': 'sqlalchemy',
        'DB_POOL_SIZE': '1',
        'DB_MAX_OVERFLOW': '0',
    }
    mount = [{'name': 'sql-socket', 'mountPath': '/cloudsql'}]
    return {
        'apiVersion': 'run.googleapis.com/v1',
        'kind': 'Job',
        'metadata': {'name': name},
        'spec': {
            'template': {
                'metadata': {
                    'annotations': {
                        'run.googleapis.com/network-interfaces': '[{"network":"default","subnetwork":"default"}]',
                        'run.googleapis.com/vpc-access-egress': 'private-ranges-only',
                        'run.googleapis.com/container-dependencies': '{"task":["cloud-sql-proxy"]}',
                    }
                },
                'spec': {
                    'taskCount': 1,
                    'parallelism': 1,
                    'template': {
                        'spec': {
                            'serviceAccountName': service_account,
                            'maxRetries': 1,
                            'timeoutSeconds': '600',
                            'containers': [
                                {
                                    'name': 'task',
                                    'image': image,
                                    'command': ['python'],
                                    'args': ['-m', 'src.api.migrate'],
                                    'env': [{'name': key, 'value': value} for key, value in env.items()]
                                    + [
                                        {'name': key, 'valueFrom': {'secretKeyRef': {'name': key, 'key': 'latest'}}}
                                        for key in secrets
                                    ],
                                    'volumeMounts': mount,
                                    'resources': {'limits': {'cpu': '1', 'memory': '512Mi'}},
                                },
                                {
                                    'name': 'cloud-sql-proxy',
                                    'image': 'gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.27.0',
                                    'args': [
                                        '--private-ip',
                                        '--enable-builtin-metrics=false',
                                        '--unix-socket=/cloudsql',
                                        '--health-check',
                                        '--http-address=0.0.0.0',
                                        '--http-port=9090',
                                        '--quitquitquit',
                                        instance,
                                    ],
                                    'volumeMounts': mount,
                                    'resources': {'limits': {'cpu': '1', 'memory': '256Mi'}},
                                    'startupProbe': {
                                        'httpGet': {'path': '/startup', 'port': 9090},
                                        'periodSeconds': 2,
                                        'failureThreshold': 30,
                                    },
                                },
                            ],
                            'volumes': [{'name': 'sql-socket', 'emptyDir': {'medium': 'Memory'}}],
                        }
                    },
                },
            }
        },
    }


if __name__ == '__main__':
    print(
        json.dumps(
            job_spec(
                os.environ.get('JOB_NAME', 'extraction-portal-migrate'),
                os.environ['IMAGE'],
                os.environ['CLOUD_SQL_INSTANCE'],
                os.environ['SERVICE_ACCOUNT'],
            )
        )
    )
