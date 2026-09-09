"""Prevent the Compose integration test runner from touching a non-test database."""
import os
import subprocess
import sys
if os.getenv('APP_ENV')!='test' or os.getenv('CONFIRM_DISPOSABLE_TEST_DATABASE')!='true':
    sys.exit('Integration tests require the separate test environment and explicit disposable-database configuration.')
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q']))
