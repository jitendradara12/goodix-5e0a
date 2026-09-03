// Goodix TLS driver for libfprint - 27c6:5e0a (Realme Book / ChicagoH)
// Reverse engineered for NixOS

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

enum bringup_states {
  BRINGUP_UPLOAD_CONFIG,
  BRINGUP_SET_DRV_STATE,
  BRINGUP_GET_POV_IMAGE,
  BRINGUP_FDT_MODE_0D_00,
  BRINGUP_FDT_MODE_0D_01,
  BRINGUP_REG_022C_030A_0,
  BRINGUP_CALIB_CAPTURE_0,
  BRINGUP_REG_022C_020A_0,
  BRINGUP_REG_022C_030A_1,
  BRINGUP_CALIB_CAPTURE_1,
  BRINGUP_REG_022C_020A_1,
  BRINGUP_REG_022C_030A_2,
  BRINGUP_CALIB_CAPTURE_2,
  BRINGUP_REG_022C_020A_2,
  BRINGUP_FDT_MODE_8D_00,
  BRINGUP_FDT_MODE_8D_01,
  BRINGUP_REG_022C_030A_3,
  BRINGUP_CALIB_CAPTURE_3,
  BRINGUP_REG_022C_020A_3,
  BRINGUP_FDT_MODE_0D_00_POST,
  BRINGUP_FDT_MODE_0D_01_POST,
  BRINGUP_SET_POV_CONFIG,
  BRINGUP_SLEEP_0,
  BRINGUP_QUERY_MCU_0,
  BRINGUP_FDT_DOWN_ARM_0,
  BRINGUP_FDT_DOWN_ARM_1,
  BRINGUP_SLEEP_1,
  BRINGUP_QUERY_MCU_1,
  BRINGUP_QUERY_MCU_2,
  BRINGUP_FDT_DOWN_ARM_2,
  BRINGUP_ENABLE_CHIP,
  BRINGUP_REG_022C_FINAL,
  BRINGUP_NUM_STATES,
};

static const char *bringup_state_names[] = {
  [BRINGUP_UPLOAD_CONFIG] = "UPLOAD_CONFIG",
  [BRINGUP_SET_DRV_STATE] = "SET_DRV_STATE",
  [BRINGUP_GET_POV_IMAGE] = "GET_POV_IMAGE",
  [BRINGUP_FDT_MODE_0D_00] = "FDT_MODE_0D_00",
  [BRINGUP_FDT_MODE_0D_01] = "FDT_MODE_0D_01",
  [BRINGUP_REG_022C_030A_0] = "REG_022C_030A_0",
  [BRINGUP_CALIB_CAPTURE_0] = "CALIB_CAPTURE_0",
  [BRINGUP_REG_022C_020A_0] = "REG_022C_020A_0",
  [BRINGUP_REG_022C_030A_1] = "REG_022C_030A_1",
  [BRINGUP_CALIB_CAPTURE_1] = "CALIB_CAPTURE_1",
  [BRINGUP_REG_022C_020A_1] = "REG_022C_020A_1",
  [BRINGUP_REG_022C_030A_2] = "REG_022C_030A_2",
  [BRINGUP_CALIB_CAPTURE_2] = "CALIB_CAPTURE_2",
  [BRINGUP_REG_022C_020A_2] = "REG_022C_020A_2",
  [BRINGUP_FDT_MODE_8D_00] = "FDT_MODE_8D_00",
  [BRINGUP_FDT_MODE_8D_01] = "FDT_MODE_8D_01",
  [BRINGUP_REG_022C_030A_3] = "REG_022C_030A_3",
  [BRINGUP_CALIB_CAPTURE_3] = "CALIB_CAPTURE_3",
  [BRINGUP_REG_022C_020A_3] = "REG_022C_020A_3",
  [BRINGUP_FDT_MODE_0D_00_POST] = "FDT_MODE_0D_00_POST",
  [BRINGUP_FDT_MODE_0D_01_POST] = "FDT_MODE_0D_01_POST",
  [BRINGUP_SET_POV_CONFIG] = "SET_POV_CONFIG",
  [BRINGUP_SLEEP_0] = "SLEEP_0",
  [BRINGUP_QUERY_MCU_0] = "QUERY_MCU_0",
  [BRINGUP_FDT_DOWN_ARM_0] = "FDT_DOWN_ARM_0",
  [BRINGUP_FDT_DOWN_ARM_1] = "FDT_DOWN_ARM_1",
  [BRINGUP_SLEEP_1] = "SLEEP_1",
  [BRINGUP_QUERY_MCU_1] = "QUERY_MCU_1",
  [BRINGUP_QUERY_MCU_2] = "QUERY_MCU_2",
  [BRINGUP_FDT_DOWN_ARM_2] = "FDT_DOWN_ARM_2",
  [BRINGUP_ENABLE_CHIP] = "ENABLE_CHIP",
  [BRINGUP_REG_022C_FINAL] = "REG_022C_FINAL",
};

static void
send_bringup_protocol (FpDevice *dev, guint8 cmd, const guint8 *payload, guint16 len,
                       gboolean reply, GoodixNoneCallback cb, gpointer user_data)
{
  GoodixCallbackInfo *cb_info = NULL;
  GoodixDefaultCallback callback = NULL;

  if (cb)
    {
      cb_info = malloc (sizeof (GoodixCallbackInfo));
      cb_info->callback = G_CALLBACK (cb);
      cb_info->user_data = user_data;
      callback = goodix_receive_none_tolerant;
    }

  goodix_send_protocol (dev, cmd, payload, len, NULL, reply, GOODIX_TIMEOUT,
                        FALSE, callback, cb_info);
}

static void
bringup_tolerant_cb (FpDevice *dev, gpointer user_data, GError *error)
{
  FpiSsm *ssm = user_data;
  if (error)
    {
      fp_dbg ("5e0a bring-up step error (tolerant): %s", error->message);
      g_error_free (error);
    }
  fpi_ssm_next_state (ssm);
}

static void
bringup_config_cb (FpDevice *dev, gboolean success, gpointer user_data, GError *error)
{
  FpiSsm *ssm = user_data;
  if (error || !success)
    {
      fp_err ("5e0a bring-up failed to upload MCU config");
      if (error)
        fpi_ssm_mark_failed (ssm, error);
      else
        fpi_ssm_mark_failed (ssm, g_error_new (FP_DEVICE_ERROR, FP_DEVICE_ERROR_PROTO, "MCU config rejected"));
      return;
    }
  fpi_ssm_next_state (ssm);
}

static void
bringup_calib_img_cb (FpDevice *dev, guint8 *data, guint16 len, gpointer user_data, GError *error)
{
  FpiSsm *ssm = user_data;
  if (error)
    {
      fp_dbg ("5e0a bring-up calib img read error (tolerant): %s", error->message);
      g_error_free (error);
    }
  else
    {
      g_message ("5e0a bring-up: calib capture completed (%u bytes)", len);
    }
  fpi_ssm_next_state (ssm);
}

static void
bringup_run_state (FpiSsm *ssm, FpDevice *dev)
{
  int state = fpi_ssm_get_cur_state (ssm);
  g_message ("5e0a bring-up stage %d/%d: %s", state + 1, BRINGUP_NUM_STATES, bringup_state_names[state]);

  switch (state)
    {
    case BRINGUP_UPLOAD_CONFIG:
      goodix_send_upload_config_mcu (dev, (guint8 *) goodix_5e0a_config,
                                     sizeof (goodix_5e0a_config), NULL,
                                     bringup_config_cb, ssm);
      break;

    case BRINGUP_SET_DRV_STATE:
      send_bringup_protocol (dev, GOODIX_CMD_SET_DRV_STATE, (const guint8 *) "\x01\x00", 2, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_GET_POV_IMAGE:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_GET_POV_IMAGE, (const guint8 *) "\x00\x00", 2, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_0D_00:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_0d_00, 27, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_0D_01:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_0d_01, 27, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_REG_022C_030A_0:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_CALIB_CAPTURE_0:
      memcpy (goodix5e0a_capture_payload, goodix_5e0a_calib_payload_0, 10);
      goodix_tls_read_image (dev, bringup_calib_img_cb, ssm);
      break;

    case BRINGUP_REG_022C_020A_0:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_REG_022C_030A_1:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_CALIB_CAPTURE_1:
      memcpy (goodix5e0a_capture_payload, goodix_5e0a_calib_payload_1, 10);
      goodix_tls_read_image (dev, bringup_calib_img_cb, ssm);
      break;

    case BRINGUP_REG_022C_020A_1:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_REG_022C_030A_2:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_CALIB_CAPTURE_2:
      memcpy (goodix5e0a_capture_payload, goodix_5e0a_calib_payload_2, 10);
      goodix_tls_read_image (dev, bringup_calib_img_cb, ssm);
      break;

    case BRINGUP_REG_022C_020A_2:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_8D_00:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_8d_00, 27, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_8D_01:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_8d_01, 27, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_REG_022C_030A_3:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_CALIB_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_CALIB_CAPTURE_3:
      memcpy (goodix5e0a_capture_payload, goodix_5e0a_calib_payload_3, 10);
      goodix_tls_read_image (dev, bringup_calib_img_cb, ssm);
      break;

    case BRINGUP_REG_022C_020A_3:
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_RESET_VAL,
                                         bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_0D_00_POST:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_0d_00, 27, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_MODE_0D_01_POST:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_FDT_MODE, goodix_5e0a_fdt_mode_0d_01, 27, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_SET_POV_CONFIG:
      goodix_send_set_pov_config (dev, goodix_5e0a_pov_config,
                                  sizeof (goodix_5e0a_pov_config), NULL,
                                  bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_SLEEP_0:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_SLEEP_MODE, (const guint8 *) "\x01\x00", 2, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_QUERY_MCU_0:
      send_bringup_protocol (dev, GOODIX_CMD_QUERY_MCU_STATE, (const guint8 *) "\x01\x01\x01", 3, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_DOWN_ARM_0:
      goodix_send_mcu_switch_to_fdt_down_noreply (dev, goodix_5e0a_fdt_up,
                                                  sizeof (goodix_5e0a_fdt_up), NULL,
                                                  bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_DOWN_ARM_1:
      goodix_send_mcu_switch_to_fdt_down_noreply (dev, goodix_5e0a_fdt_down,
                                                  sizeof (goodix_5e0a_fdt_down), NULL,
                                                  bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_SLEEP_1:
      send_bringup_protocol (dev, GOODIX_CMD_MCU_SWITCH_TO_SLEEP_MODE, (const guint8 *) "\x01\x00", 2, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_QUERY_MCU_1:
      send_bringup_protocol (dev, GOODIX_CMD_QUERY_MCU_STATE, (const guint8 *) "\x00\x00\x00", 3, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_QUERY_MCU_2:
      send_bringup_protocol (dev, GOODIX_CMD_QUERY_MCU_STATE, (const guint8 *) "\x01\x01\x01", 3, FALSE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_FDT_DOWN_ARM_2:
      goodix_send_mcu_switch_to_fdt_down_noreply (dev, goodix_5e0a_fdt_up,
                                                  sizeof (goodix_5e0a_fdt_up), NULL,
                                                  bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_ENABLE_CHIP:
      goodix_send_enable_chip (dev, TRUE, bringup_tolerant_cb, ssm);
      break;

    case BRINGUP_REG_022C_FINAL:
      /* Restore finger capture payload */
      memcpy (goodix5e0a_capture_payload, goodix_5e0a_finger_payload, 10);
      goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                         GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL,
                                         bringup_tolerant_cb, ssm);
      break;
    }
}

static void
on_bringup_complete (FpiSsm *ssm, FpDevice *dev, GError *error)
{
  if (error)
    {
      g_warning ("5e0a bring-up failed: %s", error->message);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  g_message ("5e0a bring-up complete! Device is armed and ready for scan.");
  fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), NULL);
}

static void
on_tls_activation_complete (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed during TLS activation: %s (code: %d)", error->message,
              error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }

  g_message ("5e0a TLS ready! Starting 52xD analog bring-up sequence...");
  fpi_ssm_start (fpi_ssm_new (dev, bringup_run_state, BRINGUP_NUM_STATES),
                 on_bringup_complete);
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
      fp_err ("failed during activation: %s (code: %d)", error->message,
              error->code);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
    }
}

static void
dev_activate (FpImageDevice *img_dev)
{
  FpDevice *dev = FP_DEVICE (img_dev);

  fpi_ssm_start (fpi_ssm_new (dev, activate_run_state, ACTIVATE_NUM_STATES),
                 activate_complete);
}

// ---- DEV SECTION START ----

static void
fpi_device_goodixtls5e0a_init (FpiDeviceGoodixTls5e0a *self)
{
}

static GoodixTls5xxMcuConfig
get_mcu_config (void)
{
  return (GoodixTls5xxMcuConfig){ .data = goodix_5e0a_fdt_mode, .data_len = sizeof (goodix_5e0a_fdt_mode) };
}

static GoodixTls5xxMcuConfig
get_fdt_down_config (void)
{
  return (GoodixTls5xxMcuConfig){ .data = goodix_5e0a_fdt_down, .data_len = sizeof (goodix_5e0a_fdt_down) };
}

static GoodixTls5xxMcuConfig
get_fdt_up_config (void)
{
  return (GoodixTls5xxMcuConfig){ .data = goodix_5e0a_fdt_up, .data_len = sizeof (goodix_5e0a_fdt_up) };
}

/* Geometry: 19-col 4k+3 sampling + bilinear upscale kept as-is.
 * ponytail: ceiling — dense_19x64.pgm (19x64) vs windows_unpacked.pgm (80x64)
 * neither proves nor refutes 4k+3 (interp of dense != windows, mean abs diff
 * ~44, different captures); leave algorithm alone until a same-capture PGM
 * pair exists for a real diff. */
static FpImage *
process_raw_frame (GoodixTls5xxPix * pix)
{
  guint16 samples[19][GOODIX_5E0A_HEIGHT];

  guint16 min_v = 65535, max_v = 0;
  guint active = 0;
  for (int k = 0; k < 19; ++k)
    {
      int col = 4 * k + 3;
      for (int r = 0; r < GOODIX_5E0A_HEIGHT; ++r)
        {
          guint16 v = pix[col * GOODIX_5E0A_HEIGHT + r];
          samples[k][r] = v;
          if (v > 30)
            {
              active++;
              if (v < min_v) min_v = v;
              if (v > max_v) max_v = v;
            }
        }
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

  /* Guaranteed journald output without needing debug flags */
  g_message ("5e0a frame stats: active=%u, min_v=%u, max_v=%u, range=%u, declen=%u, adj_corr=%.3f, all_corr=%.3f, dist_corr=%.3f",
             active, min_v, max_v, range, goodix5e0a_last_declen, mean_adj, mean_all, dist_0_18);

  const int W = GOODIX_5E0A_WIDTH;   // Native 80
  const int H = GOODIX_5E0A_HEIGHT;  // Native 64

  /* B9-air: empty-air frames return NULL so scan_on_read_img can poll until content. */
  if (active < 64 || range < 8)
    {
      fp_dbg ("5e0a empty air gated (active=%u < 64 || range=%u < 8)", active, range);
      return NULL;
    }

  fp_info ("5e0a finger touch accepted! active=%u, range=%u - extracting minutiae", active, range);

  FpImage *img = fp_image_new (W, H);
  img->flags |= FPI_IMAGE_PARTIAL;
  /* FPI_IMAGE_COLORS_INVERTED flipped OFF: img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED; */

  for (int r = 0; r < H; ++r)
    {
      for (int c = 0; c < W; ++c)
        {
          float pos = ((float) c - 3.0f) / 4.0f;
          float val;

          if (pos <= 0.0f)
            {
              val = (float) samples[0][r];
            }
          else if (pos >= 18.0f)
            {
              val = (float) samples[18][r];
            }
          else
            {
              int k = (int) pos;
              float c_frac = pos - (float) k;
              val = (float) samples[k][r] * (1.0f - c_frac) + (float) samples[k + 1][r] * c_frac;
            }

          int norm = (int) (((val - (float) min_v) * 255.0f) / (float) range);
          img->data[r * W + c] = (guint8) CLAMP (norm, 0, 255);
        }
    }

  return img;
}

static void
fpi_device_goodixtls5e0a_class_init (FpiDeviceGoodixTls5e0aClass * class)
{
  FpiDeviceGoodixTlsClass * gx_class = FPI_DEVICE_GOODIXTLS_CLASS (class);
  FpDeviceClass * dev_class = FP_DEVICE_CLASS (class);
  FpImageDeviceClass * img_dev_class = FP_IMAGE_DEVICE_CLASS (class);
  FpiDeviceGoodixTls5xxClass * xx_cls = FPI_DEVICE_GOODIXTLS5XX_CLASS (class);

  xx_cls->get_mcu_cfg = get_mcu_config;
  xx_cls->get_fdt_down_cfg = get_fdt_down_config;
  xx_cls->get_fdt_up_cfg = get_fdt_up_config;
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
  img_dev_class->bz3_threshold = 12;
  img_dev_class->img_width = GOODIX_5E0A_WIDTH;
  img_dev_class->img_height = GOODIX_5E0A_HEIGHT;

  fpi_device_class_auto_initialize_features (dev_class);
}
