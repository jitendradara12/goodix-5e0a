/* Exercise the production codec, not a Python reimplementation. */
#include <glib.h>
#include "goodix_proto.h"

int
main (void)
{
  for (guint command = 0; command <= 255; command++)
    {
      g_autofree guint8 *wire = NULL;
      g_autofree guint8 *payload = NULL;
      guint32 wire_len;
      guint16 payload_len;
      guint8 decoded_cmd;
      gboolean checksum, null_checksum;
      const guint8 empty[] = {0};

      goodix_encode_protocol (command, empty, 0, TRUE, FALSE, &wire, &wire_len);
      g_assert_cmpuint (wire_len, ==, 4);
      g_assert_cmpuint (wire[3], ==, (0xaa - command - 1) & 0xff);
      g_assert_true (goodix_decode_protocol (wire, wire_len, &decoded_cmd,
                                            &payload, &payload_len,
                                            &checksum, &null_checksum));
      g_assert_cmpuint (decoded_cmd, ==, command);
      g_assert_cmpuint (payload_len, ==, 0);
      g_assert_true (checksum);
    }

  /* Exercise null checksum wire handling (0x88) per ticket 52 */
  {
    g_autofree guint8 *wire = NULL;
    g_autofree guint8 *payload = NULL;
    guint32 wire_len;
    guint16 payload_len;
    guint8 decoded_cmd;
    gboolean checksum, null_checksum;
    const guint8 dummy[] = {0x01, 0x02};

    goodix_encode_protocol (0x70, dummy, sizeof (dummy), FALSE, FALSE, &wire, &wire_len);
    g_assert_true (goodix_decode_protocol (wire, wire_len, &decoded_cmd,
                                          &payload, &payload_len,
                                          &checksum, &null_checksum));
    g_assert_cmpuint (decoded_cmd, ==, 0x70);
    g_assert_cmpuint (payload_len, ==, 2);
    g_assert_true (null_checksum);
  }

  /* Exercise pack encode/decode and checksum validation */
  {
    guint8 sample_payload[16] = {0x12, 0x34};
    g_autofree guint8 *wire = NULL;
    g_autofree guint8 *payload = NULL;
    guint32 wire_len;
    guint16 payload_len;
    guint8 flags;
    gboolean valid_checksum;

    goodix_encode_pack (GOODIX_FLAGS_MSG_PROTOCOL, sample_payload, sizeof (sample_payload), FALSE, &wire, &wire_len);
    g_assert_true (goodix_decode_pack (wire, wire_len, &flags, &payload, &payload_len, &valid_checksum));
    g_assert_cmpuint (flags, ==, GOODIX_FLAGS_MSG_PROTOCOL);
    g_assert_cmpuint (payload_len, ==, sizeof (sample_payload));
    g_assert_true (valid_checksum);

    /* Corrupt the checksum byte */
    wire[sizeof (GoodixPack)] ^= 0xff;
    g_clear_pointer (&payload, g_free);
    g_assert_true (goodix_decode_pack (wire, wire_len, &flags, &payload, &payload_len, &valid_checksum));
    g_assert_false (valid_checksum);
  }

  /* Exercise zero-length wire protocol underflow guard */
  {
    guint8 zero_len_wire[4] = {0x70, 0x00, 0x00, 0x00};
    guint8 decoded_cmd;
    g_autofree guint8 *payload = NULL;
    guint16 payload_len;
    gboolean checksum, null_checksum;

    g_assert_false (goodix_decode_protocol (zero_len_wire, sizeof (zero_len_wire),
                                           &decoded_cmd, &payload, &payload_len,
                                           &checksum, &null_checksum));
  }

  return 0;
}

