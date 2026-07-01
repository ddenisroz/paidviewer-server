#!/usr/bin/env python3
# bot_service/run_tests.py
"""
Test Runner Script

Runs all tests with coverage reporting and detailed output.

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py --fast             # Run without coverage
    python run_tests.py --verbose          # Verbose output
    python run_tests.py tests/test_api/    # Run specific directory
"""
import sys
import subprocess
from pathlib import Path

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text: str):
    """Print colored header"""
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{text:^80}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")


def run_tests(args: list = None):
    """Run pytest with specified arguments"""
    if args is None:
        args = []
    
    # Base pytest command
    cmd = ["pytest"]
    
    # Add arguments
    if "--fast" in sys.argv:
        # Fast mode: no coverage
        cmd.extend(["-v", "--tb=short"])
    elif "--verbose" in sys.argv or "-v" in sys.argv:
        # Verbose mode with coverage
        cmd.extend([
            "-v",
            "--cov=.",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--tb=long"
        ])
    else:
        # Default mode
        cmd.extend([
            "-v",
            "--cov=.",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--tb=short"
        ])
    
    # Add specific test path if provided
    test_paths = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if test_paths:
        cmd.extend(test_paths)
    
    print_header("RUNNING TESTS")
    print(f"Command: {' '.join(cmd)}\n")
    
    # Run tests
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    
    return result.returncode


def run_migration_tests():
    """Run migration tests separately"""
    print_header("RUNNING MIGRATION TESTS")
    
    cmd = ["pytest", "tests/test_migrations.py", "-v"]
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    
    return result.returncode


def run_linting():
    """Run code linting"""
    print_header("RUNNING LINTING")
    
    # Ruff check
    print(f"{YELLOW}Running ruff check...{RESET}")
    result = subprocess.run(["ruff", "check", "."], cwd=Path(__file__).parent)
    
    if result.returncode != 0:
        print(f"{RED}[X] Linting failed{RESET}")
        return result.returncode
    
    print(f"{GREEN}[OK] Linting passed{RESET}")
    return 0


def print_summary(test_result: int, migration_result: int = None, lint_result: int = None):
    """Print test summary"""
    print_header("TEST SUMMARY")
    
    # Tests
    if test_result == 0:
        print(f"{GREEN}[OK] Tests: PASSED{RESET}")
    else:
        print(f"{RED}[X] Tests: FAILED{RESET}")
    
    # Migrations
    if migration_result is not None:
        if migration_result == 0:
            print(f"{GREEN}[OK] Migration Tests: PASSED{RESET}")
        else:
            print(f"{RED}[X] Migration Tests: FAILED{RESET}")
    
    # Linting
    if lint_result is not None:
        if lint_result == 0:
            print(f"{GREEN}[OK] Linting: PASSED{RESET}")
        else:
            print(f"{RED}[X] Linting: FAILED{RESET}")
    
    # Overall
    print()
    if all(r == 0 for r in [test_result, migration_result, lint_result] if r is not None):
        print(f"{GREEN}{'='*80}{RESET}")
        print(f"{GREEN}{'ALL CHECKS PASSED':^80}{RESET}")
        print(f"{GREEN}{'='*80}{RESET}")
    else:
        print(f"{RED}{'='*80}{RESET}")
        print(f"{RED}{'SOME CHECKS FAILED':^80}{RESET}")
        print(f"{RED}{'='*80}{RESET}")


def main():
    """Main test runner"""
    # Check if help requested
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        return 0
    
    # Run tests
    test_result = run_tests()
    
    # Run migration tests if not in fast mode
    migration_result = None
    if "--fast" not in sys.argv and "--no-migrations" not in sys.argv:
        migration_result = run_migration_tests()
    
    # Run linting if requested
    lint_result = None
    if "--lint" in sys.argv:
        lint_result = run_linting()
    
    # Print summary
    print_summary(test_result, migration_result, lint_result)
    
    # Return exit code
    if test_result != 0:
        return test_result
    if migration_result is not None and migration_result != 0:
        return migration_result
    if lint_result is not None and lint_result != 0:
        return lint_result
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
