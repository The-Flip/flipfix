#!/usr/bin/env python
"""
Test script to verify that changing machine status automatically updates report status
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'the_flip.settings')
django.setup()

from tickets.models import MachineInstance, ProblemReport, Maintainer

# Get a test report
report = ProblemReport.objects.filter(status=ProblemReport.STATUS_OPEN).first()
if not report:
    print("No open reports found to test with")
    exit(1)

print(f"\nTesting with report: {report}")
print(f"Initial report status: {report.status}")
print(f"Initial machine status: {report.machine.operational_status}")

# Get a maintainer
maintainer = Maintainer.objects.first()
print(f"Using maintainer: {maintainer}")

# Test 1: Set machine to "good" should close the report
print("\n" + "="*60)
print("TEST 1: Setting machine status to 'good' (should close report)")
print("="*60)
update = report.set_machine_status(MachineInstance.OPERATIONAL_STATUS_GOOD, maintainer, "Fixed the issue!")
report.refresh_from_db()
print(f"After update:")
print(f"  Report status: {report.status} (expected: closed)")
print(f"  Machine status: {report.machine.operational_status} (expected: good)")
print(f"  Update record status: {update.status}")
assert report.status == ProblemReport.STATUS_CLOSED, "Report should be closed!"
assert update.status == ProblemReport.STATUS_CLOSED, "Update should record status change!"
print("✓ TEST 1 PASSED")

# Test 2: Set machine to "broken" should open the report
print("\n" + "="*60)
print("TEST 2: Setting machine status to 'broken' (should open report)")
print("="*60)
update = report.set_machine_status(MachineInstance.OPERATIONAL_STATUS_BROKEN, maintainer, "Problem came back!")
report.refresh_from_db()
print(f"After update:")
print(f"  Report status: {report.status} (expected: open)")
print(f"  Machine status: {report.machine.operational_status} (expected: broken)")
print(f"  Update record status: {update.status}")
assert report.status == ProblemReport.STATUS_OPEN, "Report should be open!"
assert update.status == ProblemReport.STATUS_OPEN, "Update should record status change!"
print("✓ TEST 2 PASSED")

# Test 3: Set machine to "fixing" should keep report open
print("\n" + "="*60)
print("TEST 3: Setting machine status to 'fixing' (should keep report open)")
print("="*60)
update = report.set_machine_status(MachineInstance.OPERATIONAL_STATUS_FIXING, maintainer, "Working on it...")
report.refresh_from_db()
print(f"After update:")
print(f"  Report status: {report.status} (expected: open)")
print(f"  Machine status: {report.machine.operational_status} (expected: fixing)")
print(f"  Update record status: {update.status}")
assert report.status == ProblemReport.STATUS_OPEN, "Report should still be open!"
# Note: update.status should be None since status didn't change from open to open
print("✓ TEST 3 PASSED")

# Test 4: Close the report with "good" and verify it stays closed
print("\n" + "="*60)
print("TEST 4: Set to 'good' again (should close report)")
print("="*60)
update = report.set_machine_status(MachineInstance.OPERATIONAL_STATUS_GOOD, maintainer, "All fixed again!")
report.refresh_from_db()
print(f"After update:")
print(f"  Report status: {report.status} (expected: closed)")
print(f"  Machine status: {report.machine.operational_status} (expected: good)")
assert report.status == ProblemReport.STATUS_CLOSED, "Report should be closed!"
print("✓ TEST 4 PASSED")

print("\n" + "="*60)
print("ALL TESTS PASSED! ✓")
print("="*60)
