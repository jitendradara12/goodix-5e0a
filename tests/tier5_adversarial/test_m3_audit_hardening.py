"""Audit-hardening invariants.

Static checks for defects found during the full-repo audit. Each test names the
failure mode it prevents, so a future refactor cannot silently reintroduce one.
These are source-text guards, not hardware evidence: they prove the guard is
present, never that the hardware path behaves.
"""

import re
import unittest
from tests.repo_paths import repo


def read(*parts):
    with open(repo(*parts), "r", encoding="utf-8") as handle:
        return handle.read()


def function_body(src, signature):
    """Source of the function starting at `signature`, up to the next top-level one."""
    start = src.index(signature)
    return src[start:src.index("\nstatic ", start + 1)]


def strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def bytes_of(text, pattern):
    match = re.search(pattern, text, re.S)
    if not match:
        return None
    return [int(value, 16) for value in
            re.findall(r"0x([0-9a-fA-F]{2})", match.group(1))]


class TestSharedGroundTruth(unittest.TestCase):
    """goodix.c and goodix5e0a.h both carry the 5e0a capture payload."""

    def test_capture_payload_matches_header_byte_for_byte(self):
        goodix_c = read("libfprint-driver", "goodix.c")
        header = read("libfprint-driver", "goodix5e0a.h")

        from_driver = bytes_of(goodix_c,
                               r"goodix5e0a_capture_payload\[10\]\s*=\s*\{(.*?)\}")
        from_header = bytes_of(header,
                               r"goodix_5e0a_img_payload[^=]*=\s*\{(.*?)\}")
        self.assertIsNotNone(from_driver, "capture payload missing from goodix.c")
        self.assertIsNotNone(from_header, "img payload missing from goodix5e0a.h")
        self.assertEqual(len(from_driver), 10)
        self.assertEqual(from_driver, from_header,
                         "the shared 5e0a capture payload has two copies; "
                         "they must stay byte-identical")

    def test_capture_payload_is_not_a_writable_exported_global(self):
        goodix_c = read("libfprint-driver", "goodix.c")
        self.assertIn("static const guint8 goodix5e0a_capture_payload[10]", goodix_c)
        # No external declaration exists anywhere either.
        for name in ("goodix.h", "goodixtls.h", "goodix5xx.h", "goodix5e0a.h"):
            self.assertNotIn("goodix5e0a_capture_payload",
                             read("libfprint-driver", name))


class TestDeadCodeRemoved(unittest.TestCase):
    def test_data_to_str_is_gone(self):
        """Dead exported helper: defined in goodix.c, declared in goodix.h, no callers."""
        for name in ("goodix.c", "goodix.h"):
            self.assertNotIn("data_to_str", read("libfprint-driver", name))
        for name in ("goodix5e0a.c", "goodix5xx.c", "goodix511.c", "goodixtls.c"):
            self.assertNotIn("data_to_str (", read("libfprint-driver", name))


class TestPreviouslyUncoveredAuditFixes(unittest.TestCase):
    """Guard audit fixes that were initially missing from the source checks."""

    def test_read_cancellable_is_replaced_without_leaking(self):
        goodix_c = read("libfprint-driver", "goodix.c")
        init = goodix_c[goodix_c.index("goodix_dev_init (FpDevice *dev"):]
        init = init[:init.index("/* Ticket 42 conditional USB reset")]
        self.assertIn("g_clear_object (&priv->transfer_cancel_tkn);", init)
        self.assertIn("priv->transfer_cancel_tkn = g_cancellable_new ();", init)

    def test_last_declen_is_translation_unit_local(self):
        goodix5e0a_c = read("libfprint-driver", "goodix5e0a.c")
        self.assertIn("static guint32 goodix5e0a_last_declen", goodix5e0a_c)
        self.assertNotIn("extern guint16 goodix5e0a_last_declen", goodix5e0a_c)

    def test_packaged_version_matches_integration_patch(self):
        derivation = read("libfprint-goodix.nix")
        integration = read("goodix-5e0a-integration.patch")
        self.assertIn("1.94.9-goodixtls-5e0a", derivation)
        self.assertIn("+    version: '1.94.9',", integration)


class TestPeLoaderBounds(unittest.TestCase):
    """The DLL is not always the expected vendor binary: PE fields are untrusted."""

    def setUp(self):
        self.src = read("libfprint-driver", "goodix_milan.c")

    def _slice(self, start, end):
        return self.src[self.src.index(start):self.src.index(end)]

    def test_lfanew_read_is_bounded(self):
        get_export = self._slice("static void* get_export(const char *want)",
                                 "static int load_pe_file")
        self.assertIn("g_sizeofimage < 0x40", get_export)

    def test_export_table_arithmetic_is_widened(self):
        """PE-controlled offsets need widened arithmetic and exact read-width checks."""
        get_export = self._slice("static void* get_export(const char *want)",
                                 "static int load_pe_file")
        self.assertIn("(u64)e + 24 + 112 + 4 > g_sizeofimage", get_export)
        self.assertIn("g_image_data + 0x3c", get_export)
        self.assertIn("g_image_data + exprva + 24", get_export)
        self.assertNotIn("*(u32*)(g_image +", get_export)
        self.assertIn("return g_image + frva;", get_export)
        self.assertIn("(u64)exprva + 40 > g_sizeofimage", get_export)
        self.assertIn("(u64)names + (u64)nnames * 4 > g_sizeofimage", get_export)
        self.assertIn("(u64)ords + (u64)nnames * 2 > g_sizeofimage", get_export)
        self.assertIn("(u64)fns + (u64)ord * 4 + 4 > g_sizeofimage", get_export)
        for index in ("(u64)i * 4", "(u64)i * 2", "(u64)ord * 4"):
            self.assertIn(index, get_export)

    def test_section_mapping_cannot_underflow_or_wrap(self):
        """A section based past SizeOfImage used to clamp to sizeofimage - vaddr in u32."""
        mapping = self._slice("u64 seglen = (vsize > rawsize ? vsize : rawsize);",
                              "int prot = PROT_READ;")
        self.assertIn("u64 seglen", mapping)
        self.assertIn("~(u64)0xfff", mapping)
        self.assertIn("if (vaddr >= sizeofimage) continue;", mapping)
        self.assertIn("seglen > (u64)sizeofimage - vaddr", mapping)

    def test_header_map_stays_inside_the_reservation(self):
        self.assertIn("u64 hdrmap = ((u64)hdrsize + 0xfff) & ~(u64)0xfff;", self.src)
        self.assertIn("if (hdrmap > sizeofimage) hdrmap = sizeofimage;", self.src)

    def test_export_parser_uses_fully_backed_image_copy(self):
        """An in-SizeOfImage RVA in a PROT_NONE gap must not fault the parser."""
        self.assertIn("static u8 *g_image_data = NULL;", self.src)
        loader = self._slice("static int load_pe_file(const char *path)",
                             "/* Engine Function Pointers */")
        self.assertIn("g_image_data = img;", loader)
        self.assertIn("free(g_image_data);", loader)
        self.assertIn("g_image_data = NULL;", loader)


class TestShimCorrectness(unittest.TestCase):
    def setUp(self):
        self.src = read("libfprint-driver", "goodix_milan.c")

    def test_sort_is_not_quadratic(self):
        """The engine hands qsort large arrays; the old bubble sort was O(n^2)."""
        qsort = function_body(self.src, "static void MS sh_qsort(")
        self.assertNotIn("for (size_t j = i + 1", qsort)
        self.assertIn("for (width = 1; width < n;)", qsort)
        self.assertIn("size_t step = (width > n - width) ? n : width * 2;", qsort)
        self.assertIn("left = right;", qsort)
        self.assertIn("calloc(n, s)", qsort)
        # The merge path and OOM fallback both preserve stability. The old
        # non-adjacent-swap bubble sort was not stable on tied keys.
        self.assertIn("cmp(p + i * s, p + j * s) <= 0", qsort)
        self.assertIn("if (!tmp)", qsort)
        self.assertIn("cmp(p + (j - 1) * s, p + j * s) > 0", qsort)
        self.assertIn("for (size_t k = 0; k < s; k++)", qsort)

    def test_sleep_does_not_overflow_and_is_restartable(self):
        start = self.src.index("static void MS sh_Sleep(u32 ms)")
        sleep = strip_comments(function_body(self.src, "static void MS sh_Sleep(u32 ms)"))
        self.assertNotIn("usleep", sleep)
        self.assertIn("nanosleep", sleep)
        self.assertIn("errno == EINTR", sleep)

    def test_cryptgenrandom_tolerates_short_reads(self):
        gen = self.src[self.src.index("static int MS sh_CryptGenRandom("):]
        gen = gen[:gen.index("static u32 MS sh_EventUnregister")]
        self.assertIn("while (got < (size_t) len)", gen)
        self.assertIn("got += (size_t) n;", gen)

    def test_fls_alloc_respects_the_slot_table(self):
        alloc = self.src[self.src.index("static u32  MS sh_FlsAlloc(void *cb)"):]
        alloc = alloc[:alloc.index("static int  MS sh_FlsFree")]
        self.assertIn("if (g_tls_next >= TLS_SLOT_MAX) return TLS_INDEX_INVALID;", alloc)

    def test_lazy_engine_init_happens_under_the_lock(self):
        """Reading g_milan_available outside the mutex is check-then-act."""
        for signature in ("void *goodix_milan_enroll_start (int *max_images) {",
                          "int goodix_milan_verify_image (const uint8_t *pixels,",
                          "int goodix_milan_identify_image (const uint8_t *pixels,"):
            with self.subTest(entry=signature):
                body = self.src[self.src.index(signature):]
                body = body[:body.index("ensure_gs();")]
                self.assertLess(body.index("g_rec_mutex_lock (&g_milan_mutex);"),
                                body.index("!g_milan_available && !goodix_milan_init(NULL)"))


class TestErrorReporting(unittest.TestCase):
    def test_release_interface_is_never_handed_a_set_gerror(self):
        """A set *error makes g_usb_device_release_interface critical and skip the release."""
        goodix_c = read("libfprint-driver", "goodix.c")
        deinit = goodix_c[goodix_c.index("goodix_dev_deinit (FpDevice *dev, GError **error)"):]
        deinit = deinit[:deinit.index("// ---- DEV SECTION END ----")]
        self.assertIn("(error && *error) ? NULL : error", deinit)
        self.assertIn("return released && !(error && *error);", deinit)
        # The TLS shutdown that can set *error must still be guarded by clean_close.
        self.assertLess(deinit.index("if (!clean_close)"),
                        deinit.index("goodix_shutdown_tls (dev, error);"))

    def test_error_codes_are_real_enum_members(self):
        """Raw errno / byte counts are not GIOErrorEnum or GFileError values."""
        goodix_c = read("libfprint-driver", "goodix.c")
        goodixtls_c = read("libfprint-driver", "goodixtls.c")
        self.assertNotIn("g_error_new (g_io_error_quark (), sent,", goodix_c)
        self.assertNotIn("g_error_new (g_io_error_quark (), size,", goodix_c)
        self.assertIn("g_error_new (G_IO_ERROR, G_IO_ERROR_FAILED,", goodix_c)
        self.assertIn("G_IO_ERROR_CONNECTION_CLOSED", goodix_c)
        self.assertNotIn("g_set_error (error, G_FILE_ERROR, errno,", goodixtls_c)
        self.assertIn("g_file_error_from_errno (errno)", goodixtls_c)

    def test_completed_command_logs_the_real_command(self):
        """goodix_reset_state() clears priv->cmd before the old log line read it."""
        goodix_c = read("libfprint-driver", "goodix.c")
        done = goodix_c[goodix_c.index("goodix_receive_done (FpDevice *dev, guint8 *data,"):]
        done = done[:done.index("static void\ngoodix_receive_none_tolerant")]
        self.assertIn("guint8 cmd = priv->cmd;", done)
        self.assertIn('fp_dbg ("Completed command: 0x%02x", cmd);', done)


class TestBaseScanContract(unittest.TestCase):
    def test_null_image_never_reaches_the_core(self):
        """A subclass hook may be absent or return NULL; that must fail, not report NULL."""
        goodix5xx_c = read("libfprint-driver", "goodix5xx.c")
        handler = function_body(goodix5xx_c,
                                "scan_on_read_img (FpDevice *dev, guint8 *data")
        code = strip_comments(handler)
        self.assertIn("if (!img)", code)
        self.assertLess(code.index("if (!img)"),
                        code.index("fpi_image_device_image_captured"))


class TestFdtPayloadPrepend(unittest.TestCase):
    """The 0x01-prefixed tables gain a command byte, in a guint16 wire length."""

    def test_prepend_is_guarded_on_both_sides(self):
        goodix_c = read("libfprint-driver", "goodix.c")
        self.assertEqual(goodix_c.count("length < G_MAXUINT16 && mode[0] == 0x01"), 2)
        for command in ("GOODIX_CMD_MCU_SWITCH_TO_FDT_DOWN", "GOODIX_CMD_MCU_SWITCH_TO_FDT_UP"):
            with self.subTest(command=command):
                start = goodix_c.index("goodix_send_mcu_switch_to_fdt_"
                                       + command.rsplit("_", 1)[-1].lower()
                                       + " (FpDevice *dev")
                body = goodix_c[start:goodix_c.index("\n}\n", start)]
                guarded = body[body.index("if (mode && length > 0"):body.index("payload, length + 1,")]
                self.assertIn("length < G_MAXUINT16", guarded)
                self.assertIn("if (payload)", guarded)
                # Falling through still sends the caller's buffer with its own
                # free_func, so neither path leaks or double-frees.
                self.assertIn("goodix_send_protocol (dev, " + command + ", mode, length,", body)


class TestIdentifySingleSourceOfTruth(unittest.TestCase):
    def test_one_gallery_reader_and_one_engine_call(self):
        goodix5e0a_c = read("libfprint-driver", "goodix5e0a.c")
        self.assertEqual(
            goodix5e0a_c.count("fpi_device_get_identify_data (dev, &prints);"), 1)
        self.assertEqual(
            goodix5e0a_c.count("goodix_milan_identify_image (self->best_pixels,"), 1)
        self.assertIn("goodix5e0a_identify_best_frame (dev, NULL, NULL, &winner);",
                      goodix5e0a_c)
        self.assertIn(
            "goodix5e0a_identify_best_frame (dev, &matched_idx, &match_pts, NULL)",
            goodix5e0a_c)

    def test_winner_index_is_bounds_checked_before_use(self):
        goodix5e0a_c = read("libfprint-driver", "goodix5e0a.c")
        helper = goodix5e0a_c[
            goodix5e0a_c.index("goodix5e0a_identify_best_frame (FpDevice *dev"):]
        helper = helper[:helper.index("\nstatic void\ngoodix5e0a_deliver_frame")]
        self.assertIn("if (matched && idx >= 0 && (guint) idx < m)", helper)
        self.assertIn("*out_print = owners[idx];", helper)

    def test_unusable_gallery_preserves_identify_journal_line(self):
        """Non-empty galleries with no valid templates still produce a no-match log."""
        goodix5e0a_c = read("libfprint-driver", "goodix5e0a.c")
        helper = goodix5e0a_c[
            goodix5e0a_c.index("goodix5e0a_identify_best_frame (FpDevice *dev"):]
        helper = helper[:helper.index("\nstatic void\ngoodix5e0a_deliver_frame")]
        self.assertIn("5e0a Milan identify: match=0 idx=-1 pts=0 (gallery=%u usable=0)",
                      helper)
        self.assertIn("5e0a Milan identify: match=%d idx=%d pts=%d (gallery=%u usable=%u)",
                      helper)


if __name__ == "__main__":
    unittest.main()
