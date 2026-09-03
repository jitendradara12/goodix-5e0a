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

#define FP_COMPONENT "goodixtls5e0a"

#include <glib.h>
#include <string.h>

#include "drivers_api.h"
#include "goodix.h"
#include "goodix_proto.h"
#include "goodix5e0a.h"

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

static void on_config_uploaded (FpDevice *dev, gboolean success,
                                gpointer user_data, GError *error);
static void on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error);
static void on_drv_state_set (FpDevice *dev, gpointer user_data, GError *error);

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
on_register_written (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed to write sensor register: %s", error->message);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  fp_dbg ("Sensor register 0x022c configured! Activation complete and device is ready for scan.");
  fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), NULL);
}

static void
on_chip_enabled (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed to enable chip: %s", error->message);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  fp_dbg ("Chip enabled! Configuring sensor register 0x022c...");
  goodix_send_write_sensor_register (dev, GOODIX_5E0A_REG_GAIN_EXPOSURE,
                                     GOODIX_5E0A_REG_GAIN_EXPOSURE_VAL,
                                     on_register_written, NULL);
}

static void
on_drv_state_set (FpDevice *dev, gpointer user_data, GError *error)
{
  if (error)
    {
      fp_err ("failed to set drv state: %s", error->message);
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  /* ponytail: POV check (0xd2/0xac) skipped — test_touch_sensor proves touch
     works without it; add only if a Windows trace shows it required. */
  fp_dbg ("Driver state set! Enabling chip...");
  goodix_send_enable_chip (dev, TRUE, on_chip_enabled, NULL);
}

static void
on_config_uploaded (FpDevice *dev, gboolean success,
                    gpointer user_data, GError *error)
{
  if (error || !success)
    {
      fp_err ("failed to upload MCU config");
      fpi_image_device_activate_complete (FP_IMAGE_DEVICE (dev), error);
      return;
    }
  fp_dbg ("MCU config uploaded successfully after TLS! Setting drv state...");
  goodix_send_set_drv_state (dev, on_drv_state_set, NULL);
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

  fp_dbg ("TLS connection ready! Uploading MCU config (CONFIG_52XD)...");
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

  fp_info ("5e0a raw frame stats: active=%u, min_v=%u, max_v=%u, range=%u",
           active, min_v, max_v, range);

  const int W = GOODIX_5E0A_WIDTH * 2;   // 160
  const int H = GOODIX_5E0A_HEIGHT * 2;  // 128

  /* B9-air: empty-air frames must NOT full-range stretch to fake ridges.
   * ponytail: ceiling — bar (64 samples / range 8) grounded only on
   * fingerprint.pgm (697 active, range 356) vs clear-0.pgm (0 active);
   * re-tune against windows_unpacked.pgm before raising. Dim, not NULL:
   * 511's crop_frame never returns NULL and scan_on_read_img passes img
   * straight to fpi_image_device_image_captured, so NULL is unverified. */
  if (active < 64 || range < 8)
    {
      fp_dbg ("5e0a empty air gated (active=%u < 64 || range=%u < 8)", active, range);
      FpImage *dim = fp_image_new (W, H);
      dim->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;
      memset (dim->data, 0, W * H);
      return dim;
    }

  fp_info ("5e0a finger touch accepted! active=%u, range=%u - extracting minutiae", active, range);

  FpImage *img = fp_image_new (W, H);
  img->flags |= FPI_IMAGE_PARTIAL | FPI_IMAGE_COLORS_INVERTED;

  for (int r = 0; r < H; ++r)
    {
      float orig_r = (float) r / 2.0f;
      int r0 = (int) orig_r;
      int r1 = (r0 + 1 < GOODIX_5E0A_HEIGHT) ? r0 + 1 : r0;
      float r_frac = orig_r - (float) r0;

      for (int c = 0; c < W; ++c)
        {
          float orig_c = (float) c / 2.0f;
          float pos = (orig_c - 3.0f) / 4.0f;
          float val;

          if (pos <= 0.0f)
            {
              val = (float) samples[0][r0] * (1.0f - r_frac) + (float) samples[0][r1] * r_frac;
            }
          else if (pos >= 18.0f)
            {
              val = (float) samples[18][r0] * (1.0f - r_frac) + (float) samples[18][r1] * r_frac;
            }
          else
            {
              int k = (int) pos;
              float c_frac = pos - (float) k;
              float top = (float) samples[k][r0] * (1.0f - c_frac) + (float) samples[k + 1][r0] * c_frac;
              float bot = (float) samples[k][r1] * (1.0f - c_frac) + (float) samples[k + 1][r1] * c_frac;
              val = top * (1.0f - r_frac) + bot * r_frac;
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
  /* ponytail: ceiling — bz3_threshold kept at 12 (511 uses 24); no
   * windows_unpacked.pgm vs clear-0.pgm minutiae validation yet, do not tune. */
  img_dev_class->bz3_threshold = 12;
  img_dev_class->img_width = GOODIX_5E0A_WIDTH * 2;
  img_dev_class->img_height = GOODIX_5E0A_HEIGHT * 2;

  fpi_device_class_auto_initialize_features (dev_class);
}
