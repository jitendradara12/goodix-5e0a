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
  return 0;
}
