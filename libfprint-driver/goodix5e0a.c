// Goodix TLS driver for libfprint - 27c6:5e0a (Realme Book / ChicagoH)
// Reverse engineered for NixOS - Windows-faithful steady-state port (Ticket 10)

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
#include "goodix.h"
#include "goodix_proto.h"
#include "goodix5e0a.h"

guint32 goodix5e0a_last_declen = 0;

struct _FpiDeviceGoodixTls5e0a
{
  FpiDeviceGoodixTls5xx parent;

  gboolean session_started;
  FpiSsm  *scan_ssm;
  GSource *down_timeout;
};

G_DECLARE_FINAL_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a, FPI,
                      DEVICE_GOODIXTLS5E0A, FpiDeviceGoodixTls5xx);

G_DEFINE_TYPE (FpiDeviceGoodixTls5e0a, fpi_device_goodixtls5e0a,
               FPI_TYPE_DEVICE_GOODIXTLS5XX);

// ---- ACTIVATE SECTION START ----

enum activate_states {
  ACTIVATE_READ_AND_NOP,
  ACTIVATE_RESET,
  ACTIVATE_READ_CHIP_ID,
  ACTIVATE_CHECK_FW_VER,
  ACTIVATE_NUM_STATES,
};

static void
activate_run_state (FpiSsm *ssm, FpDevice *dev)
{
  switch (fpi_ssm_get_cur_state (ssm))
    {
    case ACTIVATE_READ_AND_NOP:
      goodix_start_read_loop (dev);
      goodix_send_nop (dev, goodixtls5xx_check_none, ssm);
      break;

    case ACTIVATE_RESET:
      goodix_send_reset (dev, TRUE, 20, goodixtls5xx_check_reset, ssm);
      break;

    case ACTIVATE_READ_CHIP_ID:
      goodix_send_read_sensor_register (dev, 0x0000, 4, goodixtls5xx_check_none_cmd, ssm);
      break;

    case ACTIVATE_CHECK_FW_VER:
      goodix_send_query_firmware_version (dev, goodixtls5xx_check_firmware_version, ssm);
      break;
    }
}

static void
on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed to enable chip: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  fp_dbg ("Chip enabled! Activation complete.");
  fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), NULL);
}

static void
on_config_uploaded (FpDevice *dev, gboolean success,
                    gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed to upload MCU config: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  if (!success)
    {
      fpi_image_device_activate_complete (
        FP_IMAGE_DEVICE (dev),
        g_error_new (FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO,
                     "failed to upload mcu config"));
      return;
    }

  fp_dbg ("MCU config uploaded successfully after TLS! Enabling chip...");
  goodix_send_enable_chip (dev, TRUE, on_chip_enabled, NULL);
}

static void
on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed during TLS activation: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }

  fp_dbg ("TLS connection ready! Uploading MCU config (ChicagoH GF3658 DN3)...");
  goodix_send_upload_config_mcu (dev, (guint8 *) goodix_5e0a_config,
                                 sizeof (goodix_5e0a_config), NULL,
                                 on_config_uploaded, NULL);
}

static void
activate_complete (FpiSsm *ssm, FpDevice *dev, GError *error)
{
  G_DEBUG_HERE ();
  if (!error)
    {
      goodix_tls_init (dev, on_tls_activation_complete, NULL);
    }
  else
    {
      fp_err ("failed during activation: %s (code: %d)", error->message, error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
    }
}

static void
dev_activate (FpImageDevice *img_dev)
{
  FpDevice *dev = FP_DEVICE (img_dev);
  FpiDeviceGoodixTls5e0a *self = FPI_DEVICE_GOODIXTLS5E0A (dev);

  self->session_started = FALSE;
  self->scan_ssm = NULL;
  self->down_timeout = NULL;

  fpi_ssm_start (fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES),
                 activate_complete);
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

static void goodix5e0a_on_fdt_down_reply (FpDevice *dev, guint8 *data, guint16 len,
                                          gpointer ssm, GError *err);

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
        return;
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
    {
      for (guint16 i = 4; i + 1 < len; i += 2)
        channel_energy += (guint32) data[i] | ((guint32) data[i + 1] << 8);
    }

  /* Gating rule: touch = channel-byte energy (data[2] != 0xff and channel_energy > 0), never byte0 */
  gboolean touch = (len >= 4 && data[2] != 0xff && channel_energy > 0);

  if (touch)
    {
      if (self->down_timeout)
        {
          g_source_destroy (self->down_timeout);
          self->down_timeout = NULL;
        }
      g_message ("5e0a D32 touch confirmed: mask=0x%02x energy=%u", data[2], channel_energy);
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

static void
goodix5e0a_on_read_img (FpDevice *dev, guint8 *data, guint16 len,
                        gpointer ssm, GError *err)
{
  if (err)
    {
      fpi_ssm_mark_failed (ssm, err);
      return;
    }

  goodix5e0a_last_declen = len;
  g_message ("5e0a scan_on_read_img: declen=%u", len);

  if (data && len >= 16)
    {
      g_message ("5e0a raw first 16 bytes: %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x %02x",
                 data[0], data[1], data[2], data[3], data[4], data[5], data[6], data[7],
                 data[8], data[9], data[10], data[11], data[12], data[13], data[14], data[15]);
    }

  if (data && len > 0)
    {
      g_file_set_contents ("/tmp/live_frame.raw", (const gchar *) data, len, NULL);
      fp_info ("5e0a saved /tmp/live_frame.raw (%u bytes)", len);
    }

  /* Decode into 12-bit pixel buffer */
  guint32 num_pixels = (len / 6) * 4;
  GoodixTls5xxPix *raw_frame = calloc (MAX (num_pixels, GOODIX_5E0A_FRAME_SIZE * 4), sizeof (GoodixTls5xxPix));
  goodixtls5xx_decode_frame (raw_frame, len, data);

  guint total_nonzero = 0;
  guint16 raw_min = 65535, raw_max = 0;
  for (guint32 i = 0; i < num_pixels; i++)
    {
      if (raw_frame[i] > 0)
        {
          total_nonzero++;
          if (raw_frame[i] < raw_min) raw_min = raw_frame[i];
          if (raw_frame[i] > raw_max) raw_max = raw_frame[i];
        }
    }
  g_message ("5e0a raw_frame: num_px=%u nonzero=%u min=%u max=%u",
             num_pixels, total_nonzero, raw_min == 65535 ? 0 : raw_min, raw_max);

  FpImage *img = process_raw_frame (raw_frame);
  free (raw_frame);

  if (img == NULL)
    {
      img = fp_image_new (GOODIX_5E0A_WIDTH * 2, GOODIX_5E0A_HEIGHT * 2);
      img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;
    }

  fpi_image_device_image_captured (FP_IMAGE_DEVICE (dev), img);
  fpi_ssm_next_state (ssm);
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
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }

  if (error)
    {
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

  self->session_started = FALSE;
  self->scan_ssm = NULL;
  if (self->down_timeout)
    {
      g_source_destroy (self->down_timeout);
      self->down_timeout = NULL;
    }

  goodix_reset_state (dev);
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
}

static FpImage *
process_raw_frame (GoodixTls5xxPix * pix)
{
  guint16 samples[19][GOODIX_5E0A_HEIGHT];

  guint16 min_v = 65535, max_v = 0;
  guint active = 0;
  for (int c = 0; c < GOODIX_5E0A_WIDTH; ++c)
    {
      for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
        {
          guint16 v = pix[c * GOODIX_5E0A_HEIGHT + r];
          if (v > 30)
            {
              active++;
              if (v < min_v) min_v = v;
              if (v > max_v) max_v = v;
            }
        }
    }

  for (int k = 0; k < 19; ++k)
    {
      int col = 4 * k + 3;
      for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
        samples[k][r] = pix[col * GOODIX_5E0A_HEIGHT + r];
    }

  if (min_v == 65535) min_v = 0;
  guint16 range = (max_v > min_v) ? (max_v - min_v) : 1;

  double adj_sum = 0.0;
  int adj_cnt = 0;
  double all_sum = 0.0;
  int all_cnt = 0;
  double dist_0_18 = 0.0;

  if (active >= 64)
    {
      double col_mean[19];
      double col_std[19];
      for (int k = 0; k < 19; ++k)
        {
          double sum = 0.0;
          for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
            sum += samples[k][r];
          col_mean[k] = sum / (double) GOODIX_5E0A_HEIGHT;

          double var_sum = 0.0;
          for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
            {
              double diff = samples[k][r] - col_mean[k];
              var_sum += diff * diff;
            }
          col_std[k] = sqrt (var_sum);
        }

      for (int i = 0; i < 19; ++i)
        {
          for (int j = i + 1; j < 19; ++j)
            {
              double cov = 0.0;
              for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
                cov += (samples[i][r] - col_mean[i]) * (samples[j][r] - col_mean[j]);
              double denom = col_std[i] * col_std[j];
              double r_val = (denom > 1e-6) ? (cov / denom) : 0.0;

              if (j == i + 1)
                {
                  adj_sum += r_val;
                  adj_cnt++;
                }
              if (i == 0 && j == 18)
                dist_0_18 = r_val;

              all_sum += r_val;
              all_cnt++;
            }
        }
    }

  double mean_adj = (adj_cnt > 0) ? (adj_sum / (double) adj_cnt) : 0.0;
  double mean_all = (all_cnt > 0) ? (all_sum / (double) all_cnt) : 0.0;

  GString *active_cols = g_string_new ("");
  for (int c = 0; c < GOODIX_5E0A_WIDTH; ++c)
    {
      guint32 c_sum = 0;
      for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
        c_sum += pix[c * GOODIX_5E0A_HEIGHT + r];
      if (c_sum > 0)
        g_string_append_printf (active_cols, "%d ", c);
    }
  if (active_cols->len > 0)
    g_message ("5e0a active cols: %s", active_cols->str);
  else
    g_message ("5e0a active cols: NONE (all 0)");
  g_string_free (active_cols, TRUE);

  /* Guaranteed journald output without needing debug flags */
  g_message ("5e0a frame stats: active=%u, min_v=%u, max_v=%u, range=%u, declen=%u, adj_corr=%.3f, all_corr=%.3f, dist_corr=%.3f",
             active, min_v, max_v, range, goodix5e0a_last_declen, mean_adj, mean_all, dist_0_18);

  const int W = GOODIX_5E0A_WIDTH;   // Native 80
  const int H = GOODIX_5E0A_HEIGHT;  // Native 64

  if (active < 64 || range < 8)
    return NULL;

  FpImage *img = fp_image_new (W, H);
  img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;

  for (int r = 0; r < H; ++r)
    {
      for (int c = 0; c < W; ++c)
        {
          guint16 val = pix[c * H + r];
          int norm = (int) (((val - (float) min_v) * 255.0f) / (float) range);
          img->data[r * W + c] = (guint8) CLAMP (norm, 0, 255);
        }
    }

  FpImage *scaled = fpi_image_resize (img, 2, 2);
  g_object_unref (img);
  return scaled;
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
  dev_class->nr_enroll_stages = 8;
  dev_class->scan_type = FP_SCAN_TYPE_PRESS;
  dev_class->temp_hot_seconds = -1; // Disable thermal watchdog

  img_dev_class->activate = dev_activate;
  img_dev_class->change_state = goodix5e0a_change_state;
  img_dev_class->deactivate = goodix5e0a_deactivate;
  img_dev_class->bz3_threshold = 12;
  img_dev_class->img_width = GOODIX_5E0A_WIDTH;
  img_dev_class->img_height = GOODIX_5E0A_HEIGHT;

  fpi_device_class_auto_initialize_features (dev_class);
}
