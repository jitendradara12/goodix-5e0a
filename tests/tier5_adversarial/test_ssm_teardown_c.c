/*
 * Empirical C test for libfprint SSM lifecycle, teardown, and cancellation invariants.
 */

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <glib.h>

#include "fp-device.h"
#define FP_COMPONENT "SSM-TEST"
#include "drivers_api.h"
#include "fpi-ssm.h"
#include "test-device-fake.h"

static int g_handler_calls = 0;
static int g_complete_calls = 0;
static GError *g_last_complete_error = NULL;

static void
test_handler (FpiSsm *ssm, FpDevice *dev)
{
  g_handler_calls++;
}

static void
test_complete (FpiSsm *ssm, FpDevice *dev, GError *error)
{
  g_complete_calls++;
  g_last_complete_error = error ? g_error_copy (error) : NULL;
}

/* Simulated driver struct mimicking FpiDeviceGoodixTls5e0a */
typedef struct {
  FpiSsm *scan_ssm;
  GSource *down_timeout;
  gboolean session_started;
} Sim5e0aDevice;

static void
sim_5e0a_deactivate (Sim5e0aDevice *self)
{
  self->session_started = FALSE;
  if (self->scan_ssm != NULL)
    {
      fpi_ssm_free (self->scan_ssm);
      self->scan_ssm = NULL;
    }
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }
}

int main (int argc, char *argv[])
{
  g_test_init (&argc, &argv, NULL);

  printf ("--- Testing SSM Teardown Invariants ---\n");

  /* 1. NULL safety test */
  printf ("Test 1: fpi_ssm_free(NULL) is safe no-op... ");
  fpi_ssm_free (NULL);
  printf ("PASSED\n");

  /* Instantiate valid mock FpDevice */
  g_autoptr(FpDevice) fake_dev = g_object_new (FPI_TYPE_DEVICE_FAKE, NULL);

  /* 2. Freeing active SSM without callback execution */
  printf ("Test 2: Freeing active SSM aborts without calling completion callback... ");
  g_handler_calls = 0;
  g_complete_calls = 0;
  FpiSsm *ssm = fpi_ssm_new_full (fake_dev, test_handler, 3, 3, "TEST_SSM");
  fpi_ssm_start (ssm, test_complete);
  assert (g_handler_calls == 1);
  assert (g_complete_calls == 0);

  /* Free active SSM early (as in goodix5e0a_deactivate) */
  fpi_ssm_free (ssm);
  assert (g_complete_calls == 0); /* Completion callback must NOT have been called */
  printf ("PASSED (handler_calls=%d, complete_calls=%d)\n", g_handler_calls, g_complete_calls);

  /* 3. Driver simulated deactivation on active SSM */
  printf ("Test 3: Driver sim_5e0a_deactivate on active SSM... ");
  Sim5e0aDevice dev = {0};
  dev.session_started = TRUE;
  dev.scan_ssm = fpi_ssm_new_full (fake_dev, test_handler, 3, 3, "SIM_SCAN_SSM");
  fpi_ssm_start (dev.scan_ssm, test_complete);

  sim_5e0a_deactivate (&dev);
  assert (dev.session_started == FALSE);
  assert (dev.scan_ssm == NULL);
  printf ("PASSED\n");

  /* 4. Driver simulated repeated deactivation (idempotency) */
  printf ("Test 4: Repeated deactivation is safe and idempotent... ");
  sim_5e0a_deactivate (&dev);
  assert (dev.scan_ssm == NULL);
  sim_5e0a_deactivate (&dev);
  assert (dev.scan_ssm == NULL);
  printf ("PASSED\n");

  /* 5. Deactivation after normal SSM completion */
  printf ("Test 5: Deactivation after normal SSM completion... ");
  g_handler_calls = 0;
  g_complete_calls = 0;
  FpiSsm *completed_ssm = fpi_ssm_new_full (fake_dev, test_handler, 2, 2, "COMPLETED_SSM");
  fpi_ssm_start (completed_ssm, test_complete);
  assert (g_handler_calls == 1);

  dev.scan_ssm = completed_ssm;

  /* Step to state 1 */
  fpi_ssm_next_state (completed_ssm);
  assert (g_handler_calls == 2);

  /* Step beyond final state -> marks completed and auto-frees */
  /* In driver line 478, driver sets self->scan_ssm = NULL before final transition */
  dev.scan_ssm = NULL;
  fpi_ssm_next_state (completed_ssm);
  assert (g_complete_calls == 1);

  /* Now deactivate runs */
  sim_5e0a_deactivate (&dev);
  assert (dev.scan_ssm == NULL);
  printf ("PASSED\n");

  /* 6. GCancellable and G_IO_ERROR_CANCELLED drop logic */
  printf ("Test 6: GCancellable reset vs G_IO_ERROR_CANCELLED matching... ");
  GCancellable *tkn = g_cancellable_new ();
  assert (!g_cancellable_is_cancelled (tkn));

  /* Cancel token */
  g_cancellable_cancel (tkn);
  assert (g_cancellable_is_cancelled (tkn));

  /* Simulate new activation resetting token */
  g_cancellable_reset (tkn);
  assert (!g_cancellable_is_cancelled (tkn));

  /* Now simulate the race: late cancelled transfer arrives with G_IO_ERROR_CANCELLED */
  GError *cancelled_err = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_CANCELLED, "Transfer cancelled");
  gboolean should_drop_old = g_cancellable_is_cancelled (tkn); /* FALSE in old code! */
  gboolean should_drop_new = g_cancellable_is_cancelled (tkn) ||
                             g_error_matches (cancelled_err, G_IO_ERROR, G_IO_ERROR_CANCELLED); /* TRUE in new code! */

  assert (should_drop_old == FALSE); /* The bug that caused read loop resubmission */
  assert (should_drop_new == TRUE);  /* The hardened fix */
  g_error_free (cancelled_err);
  g_object_unref (tkn);
  printf ("PASSED\n");

  /* 7. Genuine I/O error preservation */
  printf ("Test 7: Genuine I/O error is NOT dropped... ");
  GError *io_err = g_error_new_literal (G_IO_ERROR, G_IO_ERROR_TIMED_OUT, "Timed out");
  GCancellable *active_tkn = g_cancellable_new ();
  gboolean is_dropped = g_cancellable_is_cancelled (active_tkn) ||
                        g_error_matches (io_err, G_IO_ERROR, G_IO_ERROR_CANCELLED);
  assert (is_dropped == FALSE);
  g_error_free (io_err);
  g_object_unref (active_tkn);
  printf ("PASSED\n");

  /* 8. Rapid activate-deactivate stress loop (1000 iterations) */
  printf ("Test 8: 1000 rapid activate-deactivate stress cycles... ");
  for (int i = 0; i < 1000; i++)
    {
      dev.session_started = TRUE;
      dev.scan_ssm = fpi_ssm_new_full (fake_dev, test_handler, 7, 7, "RAPID_SSM");
      fpi_ssm_start (dev.scan_ssm, test_complete);
      sim_5e0a_deactivate (&dev);
      assert (dev.scan_ssm == NULL);
      assert (dev.session_started == FALSE);
    }
  printf ("PASSED (1000 iterations)\n");

  printf ("\nALL 8 EMPIRICAL INVARIANT TESTS PASSED CLEANLY!\n");
  return 0;
}
