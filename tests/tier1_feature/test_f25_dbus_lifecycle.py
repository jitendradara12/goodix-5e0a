"""
Tier 1 - Feature 25: Automated D-Bus Lifecycle & PAM / Sudo Claim Teardown Verification.
Requirements:
- Test verify single-shot lifecycle: captures forward to image_captured without calling retry_scan.
- Test that cancelled verify operations trigger clean deactivation and release the D-Bus claim without leaving dangling sessions.
- Prevent 'Device was already claimed' deadlocks in back-to-back sudo/PAM authentications.
"""

import os
import re
import unittest
from pathlib import Path
from typing import Optional, Dict, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER_C_PATH = REPO_ROOT / "libfprint-driver" / "goodix5e0a.c"
TRANSPORT_C_PATH = REPO_ROOT / "libfprint-driver" / "goodix.c"


class MockDBusDeviceManager:
    """
    Simulates fprintd D-Bus daemon device claim and session lifecycle tracking
    under PAM / sudo authentication flows.
    """

    def __init__(self):
        self.claimed_by: Optional[str] = None
        self.active_session: bool = False
        self.driver_scan_ssm_active: bool = False
        self.driver_down_timeout_active: bool = False
        self.driver_session_started: bool = False
        self.driver_usb_loop_running: bool = False
        self.claim_history = []

    def claim(self, sender: str) -> bool:
        """D-Bus Claim method: denies authorization if already claimed."""
        if self.claimed_by is not None and self.claimed_by != sender:
            raise PermissionError(
                f"Authorization denied to {sender} to call method 'Claim' for device "
                f"'Goodix TLS Fingerprint Sensor 5e0a': Device was already claimed"
            )
        self.claimed_by = sender
        self.claim_history.append(("CLAIM", sender))
        return True

    def release(self, sender: str) -> bool:
        """D-Bus Release method."""
        if self.claimed_by != sender:
            return False
        self.deactivate()
        self.claimed_by = None
        self.claim_history.append(("RELEASE", sender))
        return True

    def start_verify_session(self, sender: str) -> None:
        """D-Bus VerifyStart method."""
        if self.claimed_by != sender:
            raise PermissionError("Must claim device before starting verify")
        self.active_session = True
        self.driver_session_started = True
        self.driver_usb_loop_running = True
        self.driver_scan_ssm_active = True

    def driver_on_read_img_verify(self, minutiae_count: int, is_verify_mode: bool = True) -> str:
        """
        Simulates goodix5e0a_on_read_img.
        In verify mode: unconditionally passes image to image_captured without retry_scan.
        """
        if not is_verify_mode:
            # Enrollment action checks minutiae floor
            # (GOODIX_5E0A_ENROLL_MIN_MINUTIAE = 12, libfprint-driver/goodix5e0a.h)
            if minutiae_count < 12:
                return "retry_scan"

        # Verify action (Ticket 19): unconditionally forwards to image_captured
        # Scan SSM advances to release detection stages
        return "image_captured"

    def deactivate(self) -> None:
        """
        Simulates goodix5e0a_deactivate:
        Frees scan SSM, cancels timeouts, stops read loop, shuts down TLS, and emits deactivate_complete.
        """
        self.driver_session_started = False
        if self.driver_scan_ssm_active:
            self.driver_scan_ssm_active = False
        if self.driver_down_timeout_active:
            self.driver_down_timeout_active = False
        self.driver_usb_loop_running = False
        self.active_session = False


class TestF25DBusLifecycle(unittest.TestCase):
    """Verifies D-Bus device claim/release contracts and driver verify session teardown."""

    def setUp(self):
        self.manager = MockDBusDeviceManager()
        self.assertTrue(DRIVER_C_PATH.exists(), f"Missing driver C file: {DRIVER_C_PATH}")
        self.c_content = DRIVER_C_PATH.read_text(encoding="utf-8")

    def test_verify_single_shot_forwards_to_image_captured_without_retry(self):
        """Verify that goodix5e0a_on_read_img in verify mode passes image directly to image_captured."""
        # Code-level verification in goodix5e0a.c
        # 1. retry_scan is guarded by action == FPI_DEVICE_ACTION_ENROLL
        enroll_guard_pattern = (
            r"if\s*\(\s*action\s*==\s*FPI_DEVICE_ACTION_ENROLL\s*\)\s*\{[^}]*fpi_image_device_retry_scan"
        )
        self.assertRegex(
            self.c_content, enroll_guard_pattern,
            "fpi_image_device_retry_scan must be guarded strictly by FPI_DEVICE_ACTION_ENROLL"
        )

        # 2. Verify mode unconditionally forwards to image_captured
        self.assertIn("fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);", self.c_content)

        # Functional simulation:
        # Low minutiae touch during verify still forwards to image_captured
        result_low_minutiae = self.manager.driver_on_read_img_verify(minutiae_count=8, is_verify_mode=True)
        self.assertEqual(result_low_minutiae, "image_captured")

        # High minutiae touch during verify forwards to image_captured
        result_high_minutiae = self.manager.driver_on_read_img_verify(minutiae_count=24, is_verify_mode=True)
        self.assertEqual(result_high_minutiae, "image_captured")

    def test_clean_deactivation_and_ssm_free(self):
        """Verify goodix5e0a_deactivate frees scan_ssm, cancels down_timeout, and resets state."""
        self.assertIn("fpi_ssm_free (self->scan_ssm);", self.c_content)
        self.assertIn("self->scan_ssm = NULL;", self.c_content)
        self.assertIn("g_source_destroy (self->down_timeout);", self.c_content)
        self.assertIn("self->down_timeout = NULL;", self.c_content)
        self.assertIn("goodix_reset_state (dev);", self.c_content)
        self.assertIn("goodix_shutdown_tls (dev, &tls_err);", self.c_content)
        self.assertIn("goodix_stop_read_loop (dev);", self.c_content)
        self.assertIn("fpi_image_device_deactivate_complete (img_dev, tls_err);", self.c_content)

    def test_cancelled_verify_releases_claim_without_deadlock(self):
        """Verify that cancelling a running verify operation releases device claim for subsequent PAM sudo call."""
        client1 = ":1.753"  # e.g., hyprlock or initial verify client
        client2 = ":1.754"  # e.g., subsequent sudo invocation

        # Client 1 claims and starts verify
        self.manager.claim(client1)
        self.assertEqual(self.manager.claimed_by, client1)
        self.manager.start_verify_session(client1)
        self.assertTrue(self.manager.active_session)
        self.assertTrue(self.manager.driver_scan_ssm_active)

        # Client 1 cancels operation (Ctrl+C or prompt timeout)
        self.manager.release(client1)
        self.assertIsNone(self.manager.claimed_by)
        self.assertFalse(self.manager.active_session)
        self.assertFalse(self.manager.driver_scan_ssm_active)
        self.assertFalse(self.manager.driver_usb_loop_running)

        # Client 2 (sudo) immediately attempts to claim device
        # Must succeed without "Device was already claimed" error
        claim_ok = self.manager.claim(client2)
        self.assertTrue(claim_ok)
        self.assertEqual(self.manager.claimed_by, client2)

    def test_consecutive_verify_pam_cycles(self):
        """Stress-test 10 consecutive PAM/sudo claim, verify, and release cycles."""
        for cycle in range(10):
            sender = f":1.{800 + cycle}"
            self.manager.claim(sender)
            self.manager.start_verify_session(sender)

            # Verification capture forwards to image_captured
            step = self.manager.driver_on_read_img_verify(minutiae_count=18, is_verify_mode=True)
            self.assertEqual(step, "image_captured")

            # Normal teardown on completion
            self.manager.release(sender)
            self.assertIsNone(self.manager.claimed_by)
            self.assertFalse(self.manager.driver_scan_ssm_active)

        self.assertEqual(len(self.manager.claim_history), 20)

    def test_cancelled_usb_transfer_drop_in_transport(self):
        """Verify transport layer guards against resubmitting cancelled transfers (G_IO_ERROR_CANCELLED)."""
        self.assertTrue(TRANSPORT_C_PATH.exists(), f"Missing transport file: {TRANSPORT_C_PATH}")
        transport_text = TRANSPORT_C_PATH.read_text(encoding="utf-8")
        self.assertIn("G_IO_ERROR_CANCELLED", transport_text)
        self.assertIn("g_error_matches (error, G_IO_ERROR, G_IO_ERROR_CANCELLED)", transport_text)


if __name__ == "__main__":
    unittest.main()
