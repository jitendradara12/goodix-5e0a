// Goodix TLS driver for libfprint - 27c6:5e0a (Realme Book / ChicagoH)
// Reverse engineered for NixOS - Windows-faithful steady-state port (Ticket 10)

// Copyright (C) 2026 The libfprint Goodix 5e0a contributors

// This library is free software; you can redistribute it and/or
// modify it under the terms of the GNU Lesser General Public
// License as published by the Free Software Foundation; either
// version 2.1 of the License, or (at your option) any later version.

// This library is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// Lesser General Public License for more details.

// You should have received a copy of the GNU Lesser General Public
// License along with this library; if not, write to the Free Software
// Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

#include "drivers/goodixtls/goodix5xx.h"
#include "fp-device.h"
#include "fp-image-device.h"
#include "fp-image.h"
#include "fpi-assembling.h"
#include "fpi-context.h"
#include "fpi-image-device.h"
#include "fpi-image.h"
#include "fpi-ssm.h"
#include "glibconfig.h"
#include "gusb/gusb-device.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#define FP_COMPONENT "goodixtls5e0a"

#include <glib.h>
#include <string.h>

#include "drivers_api.h"
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wredundant-decls"
#include "nbis/include/lfs.h"
#pragma GCC diagnostic pop
#include "goodix.h"
#include "goodix_proto.h"
#include "goodix5e0a.h"

guint32 goodix5e0a_last_declen = 0;

struct _FpiDeviceGoodixTls5e0a
{
  FpiDeviceGoodixTls5xx parent;

  gboolean              session_started;
  FpiSsm               *scan_ssm;
  GSource              *down_timeout;

  /* Ticket 38 parked TLS session: deactivate leaves a live negotiated
   * context in place and stamps it; the next activate inside the TTL
   * health-checks it instead of paying the full ladder. Cleared on any
   * fallback, on destroy-path deactivate, and unconditionally on suspend
   * (sleep safety). tls_parked_gen pins the park to the post-deactivate
   * activation generation (ticket-34 counter). */
  gboolean              tls_parked;
  gint64                tls_parked_at;
  guint                 tls_parked_gen;

  /* Ticket 40 warm activation fast path: host-observed recency of the last
   * clean chip-enable (stamped ONLY in on_chip_enabled success — the last
   * host→device proof, not TLS-ready). warm_ok + same boot_seq + age <
   * GOODIX_5E0A_WARM_TTL_US lets the next claim skip RESET/CHIP_ID/OTP +
   * config upload (READ_AND_NOP + FW check + TLS kept). This is NEVER a
   * device-key claim — the handshake always runs, and warmth costs at most
   * one ladder, never a sticky dead session. warm_down_reason names the
   * last invalidation for the expired journal line; warm_attempted /
   * warm_retried bound the silent once-per-claim full-ladder retry. */
  gboolean              warm_ok;
  gint64                last_clean_mono;
  guint                 warm_boot_seq;
  const char           *warm_down_reason;
  gboolean              warm_attempted;
  gboolean              warm_retried;

  /* Ticket 39 best-of-N per-touch state: non-enroll touches collect up to
   * GOODIX_5E0A_FRAMES_PER_TOUCH frames in SCAN_5E0A_GET_IMAGE, retain the
   * highest-minutiae frame in best_img, and submit only that winner.
   * Enrollment never touches these fields. */
  guint               frame_count;
  FpImage            *best_img;
  guint               best_minutiae;
  guint               best_frame_no;
};

G_DECLARE_FINAL_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a, FPI,
                      DEVICE_GOODIXTLS5E0A, FpiDeviceGoodixTls5xx);

G_DEFINE_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a,
               FPI_TYPE_DEVICE_GOODIXTLS5XX);

static void goodix5e0a_reset_touch_frames (FpiDeviceGoodixTls5e0a *self);

// ---- ACTIVATE SECTION START ----

/* Ticket 38 parked-TLS session: a deactivated claim leaves its negotiated
 * TLS context alive for GOODIX_5E0A_TLS_PARK_TTL_US; the next claim inside
 * the window sends ONE QUERY_MCU_STATE probe with a short
 * GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS timeout and reuses the session on
 * success instead of paying the full ladder. Suspend never parks. */
#define GOODIX_5E0A_TLS_PARK_TTL_US (G_USEC_PER_SEC * 30)
#define GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS 500

/* Ticket 40 warm activation: a clean chip-enable inside this window on the
 * same device boot may skip RESET + CHIP_ID/OTP reads + config upload (the
 * FW check is kept as the warm-path discriminator). 60s outlasts the
 * back-to-back verify gap yet yields to idle/suspend drift. */
#define GOODIX_5E0A_WARM_TTL_US (G_USEC_PER_SEC * 60)

enum activate_states {
  ACTIVATE_READ_AND_NOP,
  ACTIVATE_RESET,
  ACTIVATE_READ_CHIP_ID,
  ACTIVATE_READ_OTP,
  ACTIVATE_CHECK_FW_VER,
  ACTIVATE_UPLOAD_CONFIG,
  ACTIVATE_NUM_STATES,
};

/* Ticket 26 upstream-clean strip: activation-time PSK reconciliation
 * (READ_PSK / PROVISION_PSK via 0xe4 / 0xe0) removed. Hardware record: the
 * single cold-boot bad-record-MAC event never reproduced across later
 * reboots and a true poweroff boot; the 0xe4-visible bb020001 slot always
 * reports factory bytes even while TLS with the host key succeeds (not the
 * TLS slot); 0xe0 writes are rejected in both encodings. The extra
 * round-trips cost two per-activation USB transactions plus journal noise
 * for zero benefit, and the factory-key table plus hardcoded provisioning
 * have no accepted upstream pattern (docs/UPSTREAM.md section 6).
 * Activation therefore goes CHECK_FW_VER -> UPLOAD_CONFIG -> TLS with the
 * static host key directly; any future bad-record-MAC recurrence reopens
 * ticket 26 with a pasted journal line. */

static void activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error);

static void
activate_run_state (FpiSsm *ssm, FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  /* Ticket 40 warm fast path: READ_AND_NOP is mandatory (deactivate stops
   * the read loop, jumping past state 0 hangs) and CHECK_FW_VER is kept as
   * the warm-path discriminator (fails warm fast on wrong FW). The one
   * variable — whether READ_CHIP_ID/READ_OTP also skip — resolves to skip:
   * both are zero-validation round-trips with no discriminating power on a
   * device that proved itself seconds ago. fpi_ssm_jump_to_state from inside
   * run_state has in-tree precedent (SCAN_5E0A_SESSION_D6 conditionally
   * jumps to SCAN_5E0A_FDT_DOWN); jumping to ACTIVATE_NUM_STATES completes
   * the SSM into activate_complete, i.e. the TLS handoff. The enum is NOT
   * reduced (no duplicated callbacks, no renumbered states, journal
   * continuity preserved). */
  switch (fpi_ssm_get_cur_state (ssm))
    {
    case ACTIVATE_READ_AND_NOP:
      goodix_start_read_loop (dev);
      goodix_send_nop (dev, goodixtls5xx_check_none, ssm);
      break;

    case ACTIVATE_RESET:
      if (self->warm_attempted)
        {
          fpi_ssm_jump_to_state (ssm, ACTIVATE_CHECK_FW_VER);
          return;
        }
      goodix_send_reset (dev, TRUE, 20, goodixtls5xx_check_reset, ssm);
      break;

    case ACTIVATE_READ_CHIP_ID:
      if (self->warm_attempted)
        {
          fpi_ssm_jump_to_state (ssm, ACTIVATE_CHECK_FW_VER);
          return;
        }
      goodix_send_read_sensor_register (dev, 0x0000, 4, goodixtls5xx_check_none_cmd, ssm);
      break;

    case ACTIVATE_READ_OTP:
      if (self->warm_attempted)
        {
          fpi_ssm_jump_to_state (ssm, ACTIVATE_CHECK_FW_VER);
          return;
        }
      goodix_send_read_otp (dev, goodixtls5xx_check_none_cmd, ssm);
      break;

    case ACTIVATE_CHECK_FW_VER:
      goodix_send_query_firmware_version (dev, goodixtls5xx_check_firmware_version, ssm);
      break;

    case ACTIVATE_UPLOAD_CONFIG:
      if (self->warm_attempted)
        {
          fpi_ssm_jump_to_state (ssm, ACTIVATE_NUM_STATES);
          return;
        }
      goodix_send_upload_config_mcu (dev, (guint8 *) goodix_5e0a_config,
                                     sizeof (goodix_5e0a_config), NULL,
                                     goodixtls5xx_check_config_upload, ssm);
      break;
    }
}

static void
on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  if (error)
    {
      /* Ticket 40: a dead enable poisons recency — the next claim ladder-checks. */
      self->warm_ok = FALSE;
      self->warm_down_reason = "failed-last";
      self->warm_attempted = FALSE;
      goodix_session_mark_dirty (dev);
      fp_err ("failed to enable chip: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  /* Ticket 40: the last host→device proof — stamp warmth for the next claim. */
  self->warm_ok = TRUE;
  self->last_clean_mono = g_get_monotonic_time ();
  self->warm_boot_seq = goodix_boot_seq_get (dev);
  self->warm_attempted = FALSE;
  fp_dbg ("Chip enabled! Activation complete.");
  fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), NULL);
}

/* Ticket 40 warm predicate: host-observed recency on the same device boot.
 * img_open (goodix_dev_init) brackets the whole open session, not each
 * claim, so boot_seq survives back-to-back verifies and only turns on
 * reopen/re-enumeration. TTL expiry is applied lazily by the caller. */
static gboolean
goodix5e0a_warm_fresh (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  return self->warm_ok
         && self->warm_boot_seq == goodix_boot_seq_get (dev)
         && (g_get_monotonic_time () - self->last_clean_mono) < GOODIX_5E0A_WARM_TTL_US;
}

static void
goodix5e0a_log_warm_taken (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  g_message ("5e0a warm activation: reusing MCU config (age=%.1fs, boot_seq=%u)",
             (g_get_monotonic_time () - self->last_clean_mono) / (gdouble) G_USEC_PER_SEC,
             self->warm_boot_seq);
}

/* Ticket 40 warm bring-up: the SAME SSM/engine/callbacks as the full ladder
 * — activate_run_state skips RESET/CHIP_ID/OTP/CONFIG while warm_attempted
 * is set, so this is READ_AND_NOP + FW check + TLS by construction. There
 * is never a third half-bring-up path, and the handshake is never skipped:
 * SSL_accept failure stays loud via the funnels below. */
static void
goodix5e0a_start_warm_activation (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  self->session_started = FALSE;
  self->scan_ssm = NULL;
  self->down_timeout = NULL;
  self->warm_attempted = TRUE;

  g_message ("5e0a warm path: skipping RESET + config upload, entry=CHECK_FW_VER");
  fpi_ssm_start (fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES),
                 activate_complete);
}

/* Ticket 38: today's full bring-up ladder, unchanged (reset -> config
 * upload -> handshake -> enable). Both cold activate and parked-session
 * fallback funnel through here; there is never a third half-bring-up path
 * (warm reset/config skipping is ticket 40's lane, not this one). */
static void
goodix5e0a_start_full_activation (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  self->session_started = FALSE;
  self->scan_ssm = NULL;
  self->down_timeout = NULL;
  /* Ticket 40: the full ladder never skips — a stale warm flag from an
   * orphaned attempt must not leak into this run. */
  self->warm_attempted = FALSE;

  fpi_ssm_start (fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES),
                 activate_complete);
}

/* Ticket 38 parked-session health probe reply (GoodixNoneCallback, fed via
 * goodix_receive_none like every other 0xae sender). Generation-tagged
 * like the ticket-34 TLS guard: a mismatch means a deactivate/teardown
 * landed while the probe was in flight, so drop without touching hardware
 * or completing activation. Any live error (notably the short-timeout
 * expiry on a dead device-side key, or a TLS/bus fault) shuts the parked
 * context down and runs today's full ladder exactly once — tls_parked was
 * already cleared at reuse entry, so the fallback cannot loop back here.
 * Ticket 40 refines the error half: a transport-grade miss (short-timeout
 * expiry — the device went silent) also clears warmth before the full
 * ladder; a crypto-grade miss (device answered, session key dead) preserves
 * warmth and enters the warm ladder when fresh, else the full ladder. */
static void
on_parked_health_reply (FpDevice *dev, gpointer user_data, GError *error)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);
  guint gen = GPOINTER_TO_UINT (user_data);

  if (gen != goodix_activation_gen_get (dev))
    {
      fp_dbg ("dropping stale parked-TLS health reply");
      if (error)
        g_error_free (error);
      return;
    }

  if (error)
    {
      const char *reason = "tls-error";
      gboolean transport_miss = FALSE;
      if (g_error_matches (error, G_IO_ERROR, G_IO_ERROR_TIMED_OUT))
        {
          reason = "timeout";
          transport_miss = TRUE;
        }
      g_error_free (error);
      goodix_shutdown_tls (dev, NULL);
      goodix_reset_state (dev);
      if (transport_miss)
        {
          /* Ticket 40: the device went silent — the MCU may have rebooted,
           * so config recency is void. Falls through to today's full
           * ladder, unchanged. */
          self->warm_ok = FALSE;
          self->warm_down_reason = "transport-miss";
        }
      /* Ticket 40: crypto-grade miss — the device answered but the parked
       * session key is dead, so MCU config recency still holds. A fresh
       * warm ladder (FW check + new handshake) is the right next step, not
       * a full reset; a stale/cold device falls through to the full ladder.
       * (The taken + entry journal lines are the specified ticket-40 lines;
       * no extra park-miss line is logged.) */
      else if (goodix5e0a_warm_fresh (dev))
        {
          goodix5e0a_log_warm_taken (dev);
          goodix5e0a_start_warm_activation (dev);
          return;
        }
      g_message ("5e0a parked TLS session unhealthy (%s), full re-handshake", reason);
      goodix5e0a_start_full_activation (dev);
      return;
    }

  g_message ("5e0a TLS session reused (parked %.1fs, gen=%u)",
             (g_get_monotonic_time () - self->tls_parked_at) / (gdouble) G_USEC_PER_SEC,
             gen);
  fp_dbg ("parked TLS session healthy, confirming chip enable");
  goodix_send_enable_chip (dev, TRUE, on_chip_enabled, NULL);
}

static void
on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  /* Ticket 34 stale-activation guard: a deactivate/teardown that landed
   * while the TLS handshake was in flight bumped the generation, so a
   * mismatch means this completion is orphaned — drop it without touching
   * hardware or completing activation. Live sessions always match. */
  if (GPOINTER_TO_UINT (user_data) != goodix_activation_gen_get (dev))
    {
      fp_dbg ("dropping stale TLS activation completion");
      if (error)
        g_error_free (error);
      return;
    }

  if (error)
    {
      goodix_session_mark_dirty (dev);
      /* Ticket 40 warm fallback: a failed WARM handshake retries the FULL
       * ladder once, silently (no user-visible error), loop-guarded by
       * warm_retried — warmth costs at most one ladder, never a sticky
       * dead session. The shutdown precedes the restart because
       * goodix_tls_init asserts tls_hop == NULL. */
      if (self->warm_attempted && !self->warm_retried)
        {
          self->warm_ok = FALSE;
          self->warm_down_reason = "failed-last";
          self->warm_attempted = FALSE;
          self->warm_retried = TRUE;
          g_message ("5e0a warm attempt failed (%s), retrying full ladder", error->message);
          g_error_free (error);
          goodix_shutdown_tls (dev, NULL);
          goodix_reset_state (dev);
          goodix5e0a_start_full_activation (dev);
          return;
        }
      self->warm_ok = FALSE;
      self->warm_down_reason = "failed-last";
      self->warm_attempted = FALSE;
      fp_err ("failed during TLS activation: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }

  fp_dbg ("TLS connection ready! Enabling chip...");
  goodix_send_enable_chip (dev, TRUE, on_chip_enabled, NULL);
}

static void
activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  G_DEBUG_HERE ();
  if (!error)
    {
      /* Ticket 34: capture the activation generation for the staleness guard. */
      goodix_tls_init (dev, on_tls_activation_complete,
                       GUINT_TO_POINTER (goodix_activation_gen_get (dev)));
    }
  else
    {
      goodix_session_mark_dirty (dev);
      /* Ticket 40 warm fallback: a failed WARM ladder (notably the kept FW
       * check rejecting the device) retries the FULL ladder once, silently
       * and loop-guarded — same shape as the TLS funnel above, minus the
       * TLS teardown (no session exists yet on this path). */
      if (self->warm_attempted && !self->warm_retried)
        {
          self->warm_ok = FALSE;
          self->warm_down_reason = "failed-last";
          self->warm_attempted = FALSE;
          self->warm_retried = TRUE;
          g_message ("5e0a warm attempt failed (%s), retrying full ladder", error->message);
          g_error_free (error);
          goodix5e0a_start_full_activation (dev);
          return;
        }
      self->warm_ok = FALSE;
      self->warm_down_reason = "failed-last";
      self->warm_attempted = FALSE;
      fp_err ("failed during activation: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
    }
}

static void
dev_activate (FpImageDevice *img_dev)
{
  FpDevice *dev = FP_DEVICE (img_dev);
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  /* Ticket 34: invalidate any in-flight activation from a previous session.
   * Ticket 38: capture the pre-bump generation first — a parked session is
   * pinned to exactly that generation at park time, so equality proves no
   * deactivate/teardown raced between park and this claim. */
  guint pre_gen = goodix_activation_gen_get (dev);
  guint new_gen = goodix_activation_gen_bump (dev);

  /* Ticket 39: a stale burst winner must never survive across claims. */
  goodix5e0a_reset_touch_frames (self);

  /* Ticket 40: each claim gets exactly one silent warm-to-full retry. */
  self->warm_retried = FALSE;

  if (self->tls_parked && self->tls_parked_gen == pre_gen
      && goodix_tls_is_alive (dev)
      && (g_get_monotonic_time () - self->tls_parked_at) < GOODIX_5E0A_TLS_PARK_TTL_US)
    {
      GoodixCallbackInfo *cb_info;
      GoodixQueryMcuState payload;

      /* Ticket 38 reuse attempt: claim the park now so the probe's fallback
       * below can never loop back into this branch. */
      self->tls_parked = FALSE;
      self->scan_ssm = NULL;
      self->down_timeout = NULL;
      fp_dbg ("5e0a parked TLS session candidate fresh, health-checking (gen=%u)", new_gen);
      goodix_start_read_loop (dev);
      /* ONE QUERY_MCU_STATE round-trip with a short timeout. NOTE: this
       * deliberately bypasses goodix_send_query_mcu_state, whose timeout is
       * hardcoded to GOODIX_TIMEOUT (1000ms); a dead parked session must
       * fail fast into the full-ladder fallback. Payload matches
       * goodix_send_query_mcu_state byte-for-byte. */
      cb_info = malloc (sizeof (GoodixCallbackInfo));
      cb_info->callback = G_CALLBACK (on_parked_health_reply);
      cb_info->user_data = GUINT_TO_POINTER (new_gen);
      payload.unused_flags = 0x55;
      goodix_send_protocol (dev, GOODIX_CMD_QUERY_MCU_STATE,
                            (guint8 *) &payload, sizeof (payload),
                            NULL, TRUE,
                            GOODIX_5E0A_TLS_PARK_HEALTH_TIMEOUT_MS,
                            FALSE, goodix_receive_none, cb_info);
      return;
    }

  if (self->tls_parked)
    {
      /* Ticket 38 fallback: the park is void — name the reason, shut the
       * parked context down (goodix_tls_init asserts tls_hop == NULL), and
       * run today's full ladder unchanged. */
      const char *reason;
      if (self->tls_parked_gen != pre_gen)
        reason = "gen-mismatch";
      else if (!goodix_tls_is_alive (dev))
        reason = "tls-error";
      else
        reason = "expired";
      self->tls_parked = FALSE;
      g_message ("5e0a parked TLS session unhealthy (%s), full re-handshake", reason);
      goodix_shutdown_tls (dev, NULL);
    }

  /* Ticket 40 warm fast path (branch 2 of 3 — the 38 parked-session check
   * above dominates and runs first because its gate is cheaper; the full
   * ladder below is the default). Cold session but warm device: READ_AND_NOP
   * + FW check + TLS, via the shared SSM with warm_attempted set. */
  if (goodix5e0a_warm_fresh (dev))
    {
      goodix5e0a_log_warm_taken (dev);
      goodix5e0a_start_warm_activation (dev);
      return;
    }

  /* Branch 3: today's full ladder unchanged. Name why warmth didn't apply
   * (TTL expiry invalidates lazily here; a reopened device reads as a cold
   * start — the pre-reopen recency is meaningless on the new boot). */
  {
    const char *reason;
    if (self->warm_ok && self->warm_boot_seq == goodix_boot_seq_get (dev))
      {
        reason = "ttl-expired";
        self->warm_ok = FALSE;
        self->warm_down_reason = "ttl-expired";
      }
    else if (self->warm_ok)
      {
        reason = "cold-start";
        self->warm_ok = FALSE;
        self->warm_down_reason = "cold-start";
      }
    else
      {
        reason = self->warm_down_reason ? self->warm_down_reason : "cold-start";
      }
    self->warm_attempted = FALSE;
    g_message ("5e0a warm expired: reason=%s", reason);
    goodix5e0a_start_full_activation (dev);
  }
}

// ---- ACTIVATE SECTION END ----

// -----------------------------------------------------------------------------

// ---- SCAN SECTION START (Windows-faithful steady-state port) ----

enum goodix5e0a_scan_states {
  SCAN_5E0A_SESSION_AE,
  SCAN_5E0A_SESSION_D6,
  SCAN_5E0A_FDT_DOWN,
  SCAN_5E0A_GET_IMAGE,
  SCAN_5E0A_FDT_UP_1,
  SCAN_5E0A_UP_AE,
  SCAN_5E0A_FDT_UP_2,
  SCAN_5E0A_NUM_STATES,
};

static void
send_cmd_noreply (FpDevice *dev, guint8 cmd, const guint8 *payload, guint16 len,
                  GoodixNoneCallback cb, gpointer user_data)
{
  GoodixCallbackInfo *cb_info = NULL;
  GoodixCmdCallback callback = NULL;

  if (cb)
    {
      cb_info = malloc (sizeof (GoodixCallbackInfo));
      cb_info->callback = G_CALLBACK (cb);
      cb_info->user_data = user_data;
      callback = goodix_receive_none;
    }

  goodix_send_protocol (dev, cmd, payload, len, NULL, TRUE, GOODIX_TIMEOUT,
                        FALSE, callback, cb_info);
}

static void
send_cmd_reply (FpDevice *dev, guint8 cmd, const guint8 *payload, guint16 len,
                guint timeout_ms, GoodixDefaultCallback cb, gpointer user_data)
{
  GoodixCallbackInfo *cb_info = NULL;
  GoodixCmdCallback callback = NULL;

  if (cb)
    {
      cb_info = malloc (sizeof (GoodixCallbackInfo));
      cb_info->callback = G_CALLBACK (cb);
      cb_info->user_data = user_data;
      callback = goodix_receive_default;
    }

  goodix_send_protocol (dev, cmd, payload, len, NULL, TRUE, timeout_ms,
                        TRUE, callback, cb_info);
}

static void
goodix5e0a_step_cb (FpDevice *dev, gpointer user_data, GError *error)
{
  FpiSsm *ssm = user_data;

  if (error)
    {
      fp_dbg ("5e0a step cb tolerant error: %s", error->message);
      g_error_free (error);
    }
  fpi_ssm_next_state (ssm);
}

static void
goodix5e0a_on_d6_reply (FpDevice *dev, guint8 *data, guint16 len,
                        gpointer ssm, GError *err)
{
  if (err)
    {
      fp_warn ("5e0a session d6 reply error: %s", err->message);
      g_error_free (err);
    }
  else
    {
      fp_dbg ("5e0a session d6 replied successfully (len=%u)", len);
    }
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);
  self->session_started = TRUE;
  fpi_ssm_next_state (ssm);
}

static void goodix5e0a_on_fdt_down_reply (FpDevice *dev,
                                          guint8   *data,
                                          guint16   len,
                                          gpointer  ssm,
                                          GError   *err);

static void
goodix5e0a_on_down_poll_timeout (FpDevice *dev, gpointer user_data)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  self->down_timeout = NULL;

  FpiSsm *ssm = user_data;
  if (self->scan_ssm != ssm)
    return;

  send_cmd_reply (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN,
                  goodix_5e0a_down_s12, sizeof (goodix_5e0a_down_s12),
                  0, goodix5e0a_on_fdt_down_reply, ssm);
}

static void
goodix5e0a_on_fdt_down_reply (FpDevice *dev, guint8 *data, guint16 len,
                              gpointer ssm, GError *err)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  if (err)
    {
      if (g_error_matches (err, G_IO_ERROR, G_IO_ERROR_CANCELLED))
        {
          fpi_ssm_mark_failed (ssm, err);
          return;
        }
      fpi_ssm_mark_failed (ssm, err);
      return;
    }

  guint8 status = (len > 0) ? data[0] : 0x00;

  GString *hex_str = g_string_new ("");
  for (guint16 i = 0; i < len; i++)
    g_string_append_printf (hex_str, "%02x ", data[i]);
  g_message ("5e0a D32 reply: status=0x%02x len=%u bytes=[%s]", status, len, hex_str->str);
  g_string_free (hex_str, TRUE);

  guint32 channel_energy = 0;
  if (len >= 4)
    for (guint16 i = 4; i + 1 < len; i += 2)
      channel_energy += (guint32) data[i] | ((guint32) data[i + 1] << 8);

  /* Gating rule: touch = channel-byte energy (data[2] != 0xff and channel_energy > 0), never byte0 */
  gboolean touch = (len >= 4 && data[2] != 0xff && channel_energy > 0);

  if (touch)
    {
      if (self->down_timeout)
        {
          g_source_destroy (self->down_timeout);
          self->down_timeout = NULL;
        }
      g_message ("5e0a D32 touch confirmed: mask=0x%02x energy=%u",
                 (data && len >= 3) ? data[2] : 0, channel_energy);
      fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), TRUE);
      fpi_ssm_next_state (ssm);
      return;
    }

  /* No touch (empty air or poor contact): pace re-sampling silently after 50ms */
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }
  self->down_timeout = fpi_device_add_timeout (dev, 50, goodix5e0a_on_down_poll_timeout, ssm, NULL);
}

static FpImage * process_raw_frame (GoodixTls5xxPix * pix);
static guint goodix5e0a_count_minutiae (FpImage *img);

static guint32
goodix5e0a_decode_frame (GoodixTls5xxPix *out_row_major, const guint8 *data, guint16 len)
{
  guint8 packed[GOODIX_5E0A_ACT_BYTES] = {0};
  guint32 packed_len = 0;

  if (!data)
    return 0;

  /* A canonical ChicagoH frame is 80 blocks of 132 bytes followed by a
   * four-byte footer. Each block carries 96 packed pixel bytes and 36 zero
   * padding bytes. The 80 active blocks are the natural rows of a 64x80
   * raster; keeping them in sequence avoids the destructive transpose used
   * by the superseded decoder. */
  for (guint32 block = 0; block < GOODIX_5E0A_FRAME_BLOCKS; block++)
    {
      guint32 src = block * GOODIX_5E0A_BLOCK_BYTES;
      if (src + GOODIX_5E0A_BLOCK_ACTIVE_BYTES > len)
        break;

      memcpy (packed + packed_len, data + src, GOODIX_5E0A_BLOCK_ACTIVE_BYTES);
      packed_len += GOODIX_5E0A_BLOCK_ACTIVE_BYTES;
    }

  guint32 pixel_idx = 0;
  for (guint32 i = 0; i + 6 <= packed_len && pixel_idx + 4 <= GOODIX_5E0A_FRAME_SIZE; i += 6)
    {
      const guint8 *c = packed + i;
      out_row_major[pixel_idx++] = ((c[0] & 0x0f) << 8) | c[1];
      out_row_major[pixel_idx++] = (c[3] << 4) | (c[0] >> 4);
      out_row_major[pixel_idx++] = ((c[5] & 0x0f) << 8) | c[2];
      out_row_major[pixel_idx++] = (c[4] << 4) | (c[5] >> 4);
    }

  return pixel_idx;
}

/* Ticket 39: drop any half-collected burst (unref the retained winner
 * candidate) and zero the per-touch counters. Called at touch start, claim
 * entry, and every teardown path so a stale winner never leaks. */
static void
goodix5e0a_reset_touch_frames (FpiDeviceGoodixTls5e0a *self)
{
  if (self->best_img != NULL)
    {
      g_object_unref (self->best_img);
      self->best_img = NULL;
    }
  self->frame_count = 0;
  self->best_minutiae = 0;
  self->best_frame_no = 0;
}

/* Ticket 39: hand the burst winner to the deliver tail (logs the single
 * best-frame journal line). Callers guarantee at least one banked frame. */
static FpImage *
goodix5e0a_claim_best_frame (FpiDeviceGoodixTls5e0a *self)
{
  FpImage *best;

  g_return_val_if_fail (self->best_img != NULL, NULL);
  best = self->best_img;
  g_message ("5e0a best frame %u/%u: minutiae=%u score-proxy=%u (submitting)",
             self->best_frame_no, (guint) GOODIX_5E0A_FRAMES_PER_TOUCH,
             self->best_minutiae, self->best_minutiae);
  self->best_img = NULL;
  self->best_minutiae = 0;
  self->best_frame_no = 0;
  return best;
}

/* Ticket 39: minutiae-count proxy judging for one non-enroll frame. Takes
 * ownership of img in every case: the winner is retained in best_img and
 * losers are unrefed immediately. Re-issues GET_IMAGE on the same SSM while
 * fewer than GOODIX_5E0A_FRAMES_PER_TOUCH frames are banked (TRUE means
 * another frame was already requested and the caller must return without
 * touching the SSM; FALSE means the burst is complete and the caller claims
 * the winner for the single deliver call). The proxy reuses
 * goodix5e0a_count_minutiae, the same get_minutiae parameters core matching
 * runs, because the driver never sees the core verdict. Prototyped here and
 * defined after the read callback below, so no forward declaration shadows
 * the callback definition for plain-text lookup. */
static gboolean
goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm, FpImage *img,
                            guint16 declen, guint active, guint range);

static void
goodix5e0a_on_read_img (FpDevice *dev, guint8 *data, guint16 len,
                        gpointer ssm, GError *err)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);
  FpiDeviceAction action = fpi_device_get_current_action (dev);
  FpImage *img;

  /* Ticket 39: a mid-burst read error (finger lifted between frames) falls
   * back to the best frame collected so far. With zero frames the failure
   * is reported exactly as today. */
  if (err)
    {
      if (action != FPI_DEVICE_ACTION_ENROLL && self->best_img != NULL)
        {
          g_error_free (err);
          img = goodix5e0a_claim_best_frame (self);
          goto deliver;
        }
      fpi_ssm_mark_failed (ssm, err);
      return;
    }

  /* Ticket 39: a short mid-burst read (lift between frames) submits the
   * best frame so far instead of decoding a runt. */
  if (action != FPI_DEVICE_ACTION_ENROLL && self->best_img != NULL
      && (data == NULL || len < GOODIX_5E0A_FRAME_WIRE_BYTES))
    {
      g_message ("5e0a frame %u/%u: short declen=%u, submitting best-so-far %u/%u",
                 self->frame_count + 1, (guint) GOODIX_5E0A_FRAMES_PER_TOUCH,
                 len, self->best_frame_no,
                 (guint) GOODIX_5E0A_FRAMES_PER_TOUCH);
      img = goodix5e0a_claim_best_frame (self);
      goto deliver;
    }

  goodix5e0a_last_declen = len;
  g_message ("5e0a scan_on_read_img: declen=%u", len);

  if (data && len >= 16)
    {
      g_message ("5e0a raw first 16 bytes: %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x",
                 data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7],
                 data[8], data[9], data[10], data[11], data[12], data[13], data[14], data[15]);
    }

  guint32 padding_nonzero = 0;
  if (data)
    {
      for (guint32 block = 0; block < GOODIX_5E0A_FRAME_BLOCKS; block++)
        {
          guint32 pad = block * GOODIX_5E0A_BLOCK_BYTES + GOODIX_5E0A_BLOCK_ACTIVE_BYTES;
          guint32 pad_end = MIN (pad + GOODIX_5E0A_BLOCK_BYTES - GOODIX_5E0A_BLOCK_ACTIVE_BYTES,
                                 (guint32) len);
          for (guint32 i = pad; i < pad_end; i++)
            padding_nonzero += data[i] != 0;
        }
    }

  GoodixTls5xxPix *raw_frame = calloc (GOODIX_5E0A_FRAME_SIZE, sizeof (GoodixTls5xxPix));
  guint32 decoded_pixels = goodix5e0a_decode_frame (raw_frame, data, len);

  guint total_nonzero = 0;
  guint16 raw_min = 65535, raw_max = 0;
  /* Ticket 39: contact-pixel (v > 30, the same definition process_raw_frame
   * uses) active/range for the per-frame journal line. */
  guint frame_active = 0;
  guint16 frame_min = 65535, frame_max = 0;
  for (guint32 i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      if (raw_frame[i] > 0)
        {
          total_nonzero++;
          if (raw_frame[i] < raw_min)
            raw_min = raw_frame[i];
          if (raw_frame[i] > raw_max)
            raw_max = raw_frame[i];
        }
      if (raw_frame[i] > 30)
        {
          frame_active++;
          if (raw_frame[i] < frame_min)
            frame_min = raw_frame[i];
          if (raw_frame[i] > frame_max)
            frame_max = raw_frame[i];
        }
    }
  guint frame_range = (frame_min != 65535 && frame_max > frame_min)
                      ? (guint) (frame_max - frame_min) : 0;
  g_message ("5e0a wire layout: decoded_px=%u blocks=%u active_bytes=%u padding_nonzero=%u footer_bytes=%u",
             decoded_pixels, MIN ((guint32) len / GOODIX_5E0A_BLOCK_BYTES,
                                  (guint32) GOODIX_5E0A_FRAME_BLOCKS),
             GOODIX_5E0A_BLOCK_ACTIVE_BYTES, padding_nonzero,
             len >= GOODIX_5E0A_FRAME_WIRE_BYTES ? 4 : 0);
  g_message ("5e0a row-major frame: active_px=%u nonzero=%u min=%u max=%u geometry=%dx%d (WxH)",
             decoded_pixels, total_nonzero, raw_min == 65535 ? 0 : raw_min, raw_max,
             GOODIX_5E0A_WIDTH, GOODIX_5E0A_HEIGHT);

  img = process_raw_frame (raw_frame);
  free (raw_frame);

  if (img == NULL)
    {
      img = fp_image_new (GOODIX_5E0A_SCALED_WIDTH, GOODIX_5E0A_SCALED_HEIGHT);
      img->flags = FPI_IMAGE_COLORS_INVERTED;
      img->ppmm = 500.0 / 25.4;
    }

  if (action == FPI_DEVICE_ACTION_ENROLL)
    {
      guint minutiae_count = goodix5e0a_count_minutiae (img);
      g_message ("5e0a enrollment quality check: minutiae_count=%u (floor=%d)",
                 minutiae_count, GOODIX_5E0A_ENROLL_MIN_MINUTIAE);
      if (minutiae_count < GOODIX_5E0A_ENROLL_MIN_MINUTIAE)
        {
          g_message ("5e0a enrollment touch rejected: minutiae_count=%u < %d (press firmer)",
                     minutiae_count, GOODIX_5E0A_ENROLL_MIN_MINUTIAE);
          g_object_unref (img);
          fpi_image_device_retry_scan (FP_IMAGE_DEVICE (dev), FP_DEVICE_RETRY_TOO_SHORT);
          fpi_ssm_next_state (ssm);
          return;
        }
    }

  /* Ticket 39 best-of-N: non-enroll touches re-issue GET_IMAGE from the
   * keep helper until GOODIX_5E0A_FRAMES_PER_TOUCH frames are banked; the
   * SSM does not advance between frames and only the winner reaches the
   * deliver tail below. Enrollment never enters here. */
  if (action != FPI_DEVICE_ACTION_ENROLL)
    {
      if (goodix5e0a_keep_best_frame (dev, ssm, img, len, frame_active, frame_range))
        return;
      img = goodix5e0a_claim_best_frame (self);
    }

  /* In verify mode (and all non-enroll actions), unconditionally pass the captured image
   * to fpi_image_device_image_captured without calling retry_scan. Complete the scan SSM
   * and report finger release immediately so that libfprint can finish authentication and
   * deactivate without waiting 2-5 seconds for finger lift polls (Ticket 20 latency fix). */
deliver:
  fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);

  if (action != FPI_DEVICE_ACTION_ENROLL)
    {
      self->scan_ssm = NULL;
      fpi_ssm_mark_completed (ssm);
      fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);
    }
  else
    {
      fpi_ssm_next_state (ssm);
    }
}

/* Ticket 39: minutiae-count proxy judging for one non-enroll frame. Takes
 * ownership of img in every case: the winner is retained in best_img and
 * losers are unrefed immediately. Re-issues GET_IMAGE on the same SSM while
 * fewer than GOODIX_5E0A_FRAMES_PER_TOUCH frames are banked (TRUE means
 * another frame was already requested and the caller must return without
 * touching the SSM; FALSE means the burst is complete and the caller claims
 * the winner for the single deliver call). The proxy reuses
 * goodix5e0a_count_minutiae, the same get_minutiae parameters core matching
 * runs, because the driver never sees the core verdict. */
static gboolean
goodix5e0a_keep_best_frame (FpDevice *dev, gpointer ssm, FpImage *img,
                            guint16 declen, guint active, guint range)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);
  guint minutiae = goodix5e0a_count_minutiae (img);

  self->frame_count++;
  g_message ("5e0a frame %u/%u: declen=%u active=%u range=%u minutiae=%u score-proxy=%u",
             self->frame_count, (guint) GOODIX_5E0A_FRAMES_PER_TOUCH,
             declen, active, range, minutiae, minutiae);

  if (self->best_img == NULL || minutiae > self->best_minutiae)
    {
      if (self->best_img != NULL)
        g_object_unref (self->best_img);
      self->best_img = img;
      self->best_minutiae = minutiae;
      self->best_frame_no = self->frame_count;
    }
  else
    {
      g_object_unref (img);
    }

  if (self->frame_count < GOODIX_5E0A_FRAMES_PER_TOUCH)
    {
      goodix_tls_read_image (dev, goodix5e0a_on_read_img, ssm);
      return TRUE;
    }
  return FALSE;
}

static void
goodix5e0a_on_fdt_up_reply (FpDevice *dev, guint8 *data, guint16 len,
                            gpointer ssm, GError *err)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  if (err)
    {
      fp_dbg ("5e0a D34 reply (tolerant): %s", err->message);
      g_error_free (err);
    }
  else
    {
      g_message ("5e0a D34 finger release reply: len=%u", len);
    }

  /* Mark current scan SSM completed before notifying libfprint,
   * so that when libfprint synchronously requests AWAIT_FINGER_ON,
   * the concurrency guard does not block the new scan SSM. */
  self->scan_ssm = NULL;
  fpi_ssm_next_state (ssm);
  fpi_image_device_report_finger_status (FP_IMAGE_DEVICE (dev), FALSE);
}

static void
goodix5e0a_scan_run_state (FpiSsm *ssm, FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  switch (fpi_ssm_get_cur_state (ssm))
    {
    case SCAN_5E0A_SESSION_AE:
      send_cmd_noreply (dev, GOODIX_CMD_QUERY_MCU_STATE,
                        goodix_5e0a_query_ae, sizeof (goodix_5e0a_query_ae),
                        goodix5e0a_step_cb, ssm);
      break;

    case SCAN_5E0A_SESSION_D6:
      if (self->session_started)
        {
          fpi_ssm_jump_to_state (ssm, SCAN_5E0A_FDT_DOWN);
          return;
        }
      send_cmd_reply (dev, GOODIX_CMD_SESSION_D6,
                      goodix_5e0a_session_d6, sizeof (goodix_5e0a_session_d6),
                      GOODIX_TIMEOUT, goodix5e0a_on_d6_reply, ssm);
      break;

    case SCAN_5E0A_FDT_DOWN:
      send_cmd_reply (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN,
                      goodix_5e0a_down_s12, sizeof (goodix_5e0a_down_s12),
                      0, goodix5e0a_on_fdt_down_reply, ssm);
      break;

    case SCAN_5E0A_GET_IMAGE:
      goodix_tls_read_image (dev, goodix5e0a_on_read_img, ssm);
      break;

    case SCAN_5E0A_FDT_UP_1:
      send_cmd_noreply (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_UP,
                        goodix_5e0a_up_u01, sizeof (goodix_5e0a_up_u01),
                        goodix5e0a_step_cb, ssm);
      break;

    case SCAN_5E0A_UP_AE:
      send_cmd_noreply (dev, GOODIX_CMD_QUERY_MCU_STATE,
                        goodix_5e0a_query_ae, sizeof (goodix_5e0a_query_ae),
                        goodix5e0a_step_cb, ssm);
      break;

    case SCAN_5E0A_FDT_UP_2:
      send_cmd_reply (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_UP,
                      goodix_5e0a_up_u01, sizeof (goodix_5e0a_up_u01),
                      5000, goodix5e0a_on_fdt_up_reply, ssm);
      break;
    }
}

static void
goodix5e0a_scan_complete (FpiSsm *ssm, FpDevice *dev, GError *error)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  self->scan_ssm = NULL;
  /* Ticket 39: never carry a burst winner past SSM completion. */
  goodix5e0a_reset_touch_frames (self);
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }

  if (error)
    {
      /* Ticket 42: scan error voids reset-skipping. */
      goodix_session_mark_dirty (dev);
      self->warm_ok = FALSE;
      fp_err ("5e0a failed to scan: %s (code: %d)", error->message, error->code);
      fpi_image_device_session_error (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  fp_dbg ("5e0a finished scan stage");
}

static void
goodix5e0a_scan_start (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  if (self->scan_ssm != NULL)
    {
      fp_dbg ("5e0a scan SSM already active, ignoring start request");
      return;
    }

  /* Ticket 39: each touch starts with an empty burst. */
  goodix5e0a_reset_touch_frames (self);

  self->scan_ssm = fpi_ssm_new (dev, goodix5e0a_scan_run_state, SCAN_5E0A_NUM_STATES);
  fpi_ssm_start (self->scan_ssm, goodix5e0a_scan_complete);
}

static void
goodix5e0a_change_state (FpImageDevice *img_dev, FpiImageDeviceState state)
{
  if (state == FPI_IMAGE_DEVICE_STATE_AWAIT_FINGER_ON)
    goodix5e0a_scan_start (FP_DEVICE (img_dev));
}

static void
goodix5e0a_deactivate (FpImageDevice *img_dev)
{
  FpDevice *dev = FP_DEVICE (img_dev);
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  /* Ticket 39: never carry a burst winner past deactivation. */
  goodix5e0a_reset_touch_frames (self);

  /* Ticket 34: orphan any in-flight TLS activation; its completion will drop. */
  goodix_activation_gen_bump (dev);

  self->session_started = FALSE;
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }

  goodix_reset_state (dev);
  if (self->scan_ssm != NULL)
    {
      fpi_ssm_free (self->scan_ssm);
      self->scan_ssm = NULL;
    }

  /* Ticket 38 park branch: the negotiated TLS session (and chip-enabled
   * state) survives across claims while its context is alive — stop the
   * read loop only, stamp the park, and let the next activate health-check
   * it. Destroy branch is full shutdown; only a successful chip enable may
   * park, because failure funnels can leave a host TLS context allocated. */
  if (goodix_tls_is_alive (dev) && self->warm_ok)
    {
      goodix_stop_read_loop (dev);
      self->tls_parked = TRUE;
      self->tls_parked_at = g_get_monotonic_time ();
      self->tls_parked_gen = goodix_activation_gen_get (dev);
      goodix_session_mark_clean (dev);
      fp_dbg ("5e0a parking live TLS session (gen=%u)", self->tls_parked_gen);
      fpi_image_device_deactivate_complete (img_dev, NULL);
      return;
    }

  self->tls_parked = FALSE;
  goodix_session_mark_dirty (dev);
  GError *tls_err = NULL;
  goodix_shutdown_tls (dev, &tls_err);
  goodix_stop_read_loop (dev);
  fpi_image_device_deactivate_complete (img_dev, tls_err);
}

// ---- SCAN SECTION END ----

static void
fpi_device_goodixtls5e0a_init (FpiDeviceGoodixTls5e0a *self)
{
  self->session_started = FALSE;
  self->scan_ssm = NULL;
  self->down_timeout = NULL;
  self->tls_parked = FALSE;
  self->tls_parked_at = 0;
  self->tls_parked_gen = 0;
  self->warm_ok = FALSE;
  self->last_clean_mono = 0;
  self->warm_boot_seq = 0;
  self->warm_down_reason = "cold-start";
  self->warm_attempted = FALSE;
  self->warm_retried = FALSE;
  self->frame_count = 0;
  self->best_img = NULL;
  self->best_minutiae = 0;
  self->best_frame_no = 0;
}

static double
goodix5e0a_axis_correlation (const GoodixTls5xxPix *pix,
                             int                    width,
                             int                    height,
                             int                    dx,
                             int                    dy)
{
  double sum_a = 0.0, sum_b = 0.0;
  guint count = 0;

  for (int y = 0; y + dy < height; y++)
    for (int x = 0; x + dx < width; x++)
      {
        sum_a += pix[y * width + x];
        sum_b += pix[(y + dy) * width + x + dx];
        count++;
      }

  if (count == 0)
    return 0.0;

  double mean_a = sum_a / count;
  double mean_b = sum_b / count;
  double covariance = 0.0, variance_a = 0.0, variance_b = 0.0;

  for (int y = 0; y + dy < height; y++)
    for (int x = 0; x + dx < width; x++)
      {
        double a = pix[y * width + x] - mean_a;
        double b = pix[(y + dy) * width + x + dx] - mean_b;
        covariance += a * b;
        variance_a += a * a;
        variance_b += b * b;
      }

  double denominator = sqrt (variance_a * variance_b);
  return denominator > 1e-6 ? covariance / denominator : 0.0;
}

static FpImage *
process_raw_frame (GoodixTls5xxPix * pix)
{
  const int W = GOODIX_5E0A_WIDTH;
  const int H = GOODIX_5E0A_HEIGHT;
  const int dst_w = GOODIX_5E0A_SCALED_WIDTH;
  const int dst_h = GOODIX_5E0A_SCALED_HEIGHT;

  guint16 min_v = 65535, max_v = 0;
  guint active = 0;

  for (int r = 0; r < H; ++r)
    {
      for (int c = 0; c < W; ++c)
        {
          guint16 v = pix[r * W + c];
          if (v > 30)
            {
              active++;
              if (v < min_v)
                min_v = v;
              if (v > max_v)
                max_v = v;
            }
        }
    }

  if (min_v == 65535)
    min_v = 0;
  guint16 range = (max_v > min_v) ? (max_v - min_v) : 1;

  double horizontal_corr = goodix5e0a_axis_correlation (pix, W, H, 1, 0);
  double vertical_corr = goodix5e0a_axis_correlation (pix, W, H, 0, 1);
  double horizontal_lag4_corr = goodix5e0a_axis_correlation (pix, W, H, 4, 0);

  GString *active_cols = g_string_new ("");
  for (int c = 0; c < W; ++c)
    {
      guint32 c_sum = 0;
      for (int r = 0; r < H; ++r)
        c_sum += pix[r * W + c];
      if (c_sum > 0)
        g_string_append_printf (active_cols, "%d ", c);
    }
  if (active_cols->len > 0)
    g_message ("5e0a active cols: %s", active_cols->str);
  else
    g_message ("5e0a active cols: NONE (all 0)");
  g_string_free (active_cols, TRUE);

  /* Guaranteed journald output without needing debug flags */
  g_message ("5e0a frame stats: active=%u, min_v=%u, max_v=%u, range=%u, declen=%u, h_corr=%.3f, v_corr=%.3f, h_lag4_corr=%.3f (native %dx%d WxH)",
             active, min_v, max_v, range, goodix5e0a_last_declen,
             horizontal_corr, vertical_corr, horizontal_lag4_corr, W, H);

  if (active < 64 || range < 8)
    return NULL;

  /* Remove the slowly varying pressure/offset field before global scaling.
   * A 3x3 local mean is the smallest window that removes this field without
   * averaging across a full ridge period. */
  float residual[GOODIX_5E0A_FRAME_SIZE];
  float residual_min = G_MAXFLOAT;
  float residual_max = -G_MAXFLOAT;
  for (int y = 0; y < H; y++)
    {
      for (int x = 0; x < W; x++)
        {
          guint32 local_sum = 0;
          guint local_count = 0;
          for (int yy = MAX (0, y - 1); yy <= MIN (H - 1, y + 1); yy++)
            for (int xx = MAX (0, x - 1); xx <= MIN (W - 1, x + 1); xx++)
              {
                local_sum += pix[yy * W + xx];
                local_count++;
              }

          float value = pix[y * W + x] - (float) local_sum / local_count;
          residual[y * W + x] = value;
          residual_min = MIN (residual_min, value);
          residual_max = MAX (residual_max, value);
        }
    }

  float residual_range = residual_max - residual_min;
  g_message ("5e0a local contrast: min=%.2f max=%.2f range=%.2f window=3x3 gain=%.2f",
             residual_min, residual_max, residual_range, GOODIX_5E0A_CONTRAST_GAIN);
  if (residual_range < 1.0f)
    return NULL;

  guint8 normalized[GOODIX_5E0A_FRAME_SIZE];
  for (guint i = 0; i < GOODIX_5E0A_FRAME_SIZE; i++)
    {
      int value = (int) roundf (128.0f + residual[i] * GOODIX_5E0A_CONTRAST_GAIN);
      normalized[i] = (guint8) CLAMP (value, 0, 255);
    }

  /* Create the scaled 128x160 image directly via bilinear upscaling.
   * Use FPI_IMAGE_COLORS_INVERTED for capacitive ridges (high ADC = black).
   * Omit FPI_IMAGE_PARTIAL so remove_perimeter_pts=0 retains edge minutiae. */
  FpImage *scaled = fp_image_new (dst_w, dst_h);
  scaled->flags = FPI_IMAGE_COLORS_INVERTED;
  scaled->ppmm = 500.0 / 25.4;

  for (int y = 0; y < dst_h; y++)
    {
      float src_y = (y + 0.5f) * 0.5f - 0.5f;
      if (src_y < 0.0f)
        src_y = 0.0f;
      int y0 = (int) src_y;
      int y1 = (y0 + 1 < H) ? y0 + 1 : y0;
      float y_frac = src_y - (float) y0;

      for (int x = 0; x < dst_w; x++)
        {
          float src_x = (x + 0.5f) * 0.5f - 0.5f;
          if (src_x < 0.0f)
            src_x = 0.0f;
          int x0 = (int) src_x;
          int x1 = (x0 + 1 < W) ? x0 + 1 : x0;
          float x_frac = src_x - (float) x0;

          float top = (float) normalized[y0 * W + x0] * (1.0f - x_frac) + (float) normalized[y0 * W + x1] * x_frac;
          float bot = (float) normalized[y1 * W + x0] * (1.0f - x_frac) + (float) normalized[y1 * W + x1] * x_frac;
          float val = top * (1.0f - y_frac) + bot * y_frac;
          int norm = (int) roundf (val);
          scaled->data[y * dst_w + x] = (guint8) CLAMP (norm, 0, 255);
        }
    }

  g_message ("5e0a scaled image: %dx%d (WxH) flags=0x%02x active=%u range=%u ppmm=%.3f",
             scaled->width, scaled->height, scaled->flags, active, range, scaled->ppmm);
  return scaled;
}

static guint
goodix5e0a_count_minutiae (FpImage *img)
{
  if (!img || !img->data)
    return 0;

  int w = img->width;
  int h = img->height;
  unsigned char *buf = g_memdup2 (img->data, w * h);

  if (img->flags & FPI_IMAGE_COLORS_INVERTED)
    for (int i = 0; i < w * h; i++)
      buf[i] = 255 - buf[i];

  LFSPARMS parms = g_lfsparms_V2;
  parms.remove_perimeter_pts = 0;
  double ppmm = img->ppmm > 0 ? img->ppmm : (500.0 / 25.4);

  MINUTIAE *minutiae = NULL;
  int *qmap = NULL, *dmap = NULL, *lcmap = NULL, *lfmap = NULL, *hcmap = NULL;
  int mw, mh, bw, bh, bd;
  unsigned char *bdata = NULL;

  int ret = get_minutiae (&minutiae, &qmap, &dmap, &lcmap, &lfmap, &hcmap,
                          &mw, &mh, &bdata, &bw, &bh, &bd,
                          buf, w, h, 8, ppmm, &parms);
  guint count = (ret == 0 && minutiae) ? minutiae->num : 0;

  g_free (buf);
  if (minutiae)
    free_minutiae (minutiae);
  if (qmap)
    g_free (qmap);
  if (dmap)
    g_free (dmap);
  if (lcmap)
    g_free (lcmap);
  if (lfmap)
    g_free (lfmap);
  if (hcmap)
    g_free (hcmap);
  if (bdata)
    g_free (bdata);

  return count;
}

void
goodix5e0a_suspend (FpDevice *dev)
{
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);
  FpiDeviceAction action = fpi_device_get_current_action (dev);

  fp_dbg ("5e0a suspend requested during action: %d", action);

  /* Ticket 34 staleness guard: orphan any in-flight TLS handshake/activation */
  goodix_activation_gen_bump (dev);

  /* Ticket 38: sleep safety is non-negotiable — never carry a parked
   * session across suspend; the unconditional shutdown below stands. */
  self->tls_parked = FALSE;
  goodix_session_mark_dirty (dev);
  /* Ticket 40: sleep safety extends to warmth — suspend always resets warm
   * state, unconditionally and non-negotiably. */
  self->warm_ok = FALSE;
  self->warm_down_reason = "suspended";
  self->warm_attempted = FALSE;
  /* Ticket 39: never carry a burst winner across suspend. */
  goodix5e0a_reset_touch_frames (self);
  self->session_started = FALSE;
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }

  /* Reset in-flight protocol commands and timeout */
  goodix_reset_state (dev);

  /* Free in-flight scan state machine */
  if (self->scan_ssm != NULL)
    {
      fpi_ssm_free (self->scan_ssm);
      self->scan_ssm = NULL;
    }

  /* Terminate background read loop and cancel transfers */
  goodix_stop_read_loop (dev);

  /* Tear down TLS context */
  goodix_shutdown_tls (dev, NULL);

  /* Complete suspend with NOT_SUPPORTED to trigger clean core deactivation
   * of the interactive task, releasing PAM claims before sleep. */
  fpi_device_suspend_complete (dev, fpi_device_error_new (FP_DEVICE_ERROR_NOT_SUPPORTED));
}

void
goodix5e0a_resume (FpDevice *dev)
{
  fp_dbg ("5e0a resume requested");

  /* Device state was cleaned up during suspend; complete resume immediately.
   * Subsequent user claims will trigger clean open/activate and hardware re-priming. */
  fpi_device_resume_complete (dev, NULL);
}

static void
fpi_device_goodixtls5e0a_class_init (FpiDeviceGoodixTls5e0aClass * class)
{
  FpiDeviceGoodixTlsClass * gx_class = FPI_DEVICE_GOODIXTLS_CLASS (class);
  FpDeviceClass * dev_class = FP_DEVICE_CLASS (class);
  FpImageDeviceClass * img_dev_class = FP_IMAGE_DEVICE_CLASS (class);
  FpiDeviceGoodixTls5xxClass * xx_cls = FPI_DEVICE_GOODIXTLS5XX_CLASS (class);

  xx_cls->process_raw_frame = process_raw_frame;
  xx_cls->scan_height = GOODIX_5E0A_HEIGHT;
  xx_cls->scan_width = GOODIX_5E0A_WIDTH;
  xx_cls->psk = goodix_5e0a_psk;
  xx_cls->psk_flags = GOODIX_5E0A_PSK_FLAGS;
  xx_cls->psk_len = sizeof (goodix_5e0a_psk);
  xx_cls->firmware_version = GOODIX_5E0A_FIRMWARE_VERSION;
  xx_cls->reset_number = GOODIX_5E0A_RESET_NUMBER;
  xx_cls->has_calibration = FALSE;

  gx_class->interface = GOODIX_5E0A_INTERFACE;
  gx_class->ep_in = GOODIX_5E0A_EP_IN;
  gx_class->ep_out = GOODIX_5E0A_EP_OUT;

  dev_class->id = "goodixtls5e0a";
  dev_class->full_name = "Goodix TLS Fingerprint Sensor 5e0a";
  dev_class->type = FP_DEVICE_TYPE_USB;
  dev_class->id_table = goodix_5e0a_id_table;
  dev_class->nr_enroll_stages = 12;
  dev_class->scan_type = FP_SCAN_TYPE_PRESS;
  dev_class->temp_hot_seconds = -1; // Disable thermal watchdog
  dev_class->suspend = goodix5e0a_suspend;
  dev_class->resume = goodix5e0a_resume;

  img_dev_class->activate = dev_activate;
  img_dev_class->change_state = goodix5e0a_change_state;
  img_dev_class->deactivate = goodix5e0a_deactivate;
  img_dev_class->bz3_threshold = 12;
  img_dev_class->img_width = GOODIX_5E0A_SCALED_WIDTH;
  img_dev_class->img_height = GOODIX_5E0A_SCALED_HEIGHT;

  fpi_device_class_auto_initialize_features (dev_class);
}
