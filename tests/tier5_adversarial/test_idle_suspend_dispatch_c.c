/* Minimal offline reproducer: public suspend/resume bypass idle driver hooks.
 * Uses libfprint's fake virtual device. No Goodix code or USB access needed.
 */
#include "drivers_api.h"
#include "test-device-fake.h"

static guint suspend_calls, resume_calls;

static void suspend_hook (FpDevice *dev)
{
  suspend_calls++;
  fpi_device_suspend_complete (dev, NULL);
}

static void resume_hook (FpDevice *dev)
{
  resume_calls++;
  fpi_device_resume_complete (dev, NULL);
}

int main (int argc, char **argv)
{
  g_test_init (&argc, &argv, NULL);
  FpDeviceClass *klass = g_type_class_ref (FPI_TYPE_DEVICE_FAKE);
  klass->type = FP_DEVICE_TYPE_VIRTUAL;
  klass->suspend = suspend_hook;
  klass->resume = resume_hook;
  g_autoptr(FpDevice) dev = g_object_new (FPI_TYPE_DEVICE_FAKE, NULL);
  g_autoptr(GError) error = NULL;
  g_assert_cmpint (fpi_device_get_current_action (dev), ==, FPI_DEVICE_ACTION_NONE);
  g_assert_true (fp_device_suspend_sync (dev, NULL, &error));
  g_assert_no_error (error);
  g_assert_true (fp_device_resume_sync (dev, NULL, &error));
  g_assert_no_error (error);
  g_print ("public suspend/resume succeeded; driver hooks: suspend=%u resume=%u\n",
           suspend_calls, resume_calls);
  /* Upstream contract (fpi-device.c:1596): with current_action NONE, suspend
   * completes without invoking the driver hook; the hook is reserved for
   * ENROLL/VERIFY/IDENTIFY/CAPTURE (fpi-device.h:111). An idle suspend can
   * therefore never tear down parked TLS; safety on resume is delegated to
   * the driver's health-probe gate, covered by
   * /goodix/lifecycle/public-idle-suspend in test_suspend_recovery_c.c. */
  g_assert_cmpuint (suspend_calls, ==, 0);
  g_assert_cmpuint (resume_calls, ==, 0);
  g_type_class_unref (klass);
  return 0;
}
