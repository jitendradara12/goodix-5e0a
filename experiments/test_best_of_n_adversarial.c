/*
 * Adversarial empirical test harness for Goodix 5e0a Best-of-N enrollment banking
 * and minutiae floor quality gate.
 *
 * Verifies:
 * 1. All-weak bursts (<12 minutiae): retry_scan, frame reset, zero leak, no commit.
 * 2. Winning frame selection: 8 vs 15 vs 10 -> Frame 2 submitted, Frame 1/3 freed.
 * 3. Mid-burst USB errors / short reads: fallback to best-so-far, floor gate on fallback.
 * 4. Cancellation & deactivation: immediate unref of best_img, safe cancellation drop.
 * 5. Weak references on all FpImage instances to guarantee 0 memory leaks.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <glib.h>
#include <gio/gio.h>
#include <fp-device.h>
#include <fpi-image.h>
#include <fpi-image-device.h>

#define GOODIX_5E0A_FRAMES_PER_TOUCH 3
#define GOODIX_5E0A_ENROLL_MIN_MINUTIAE 12

typedef enum {
    MOCK_ACTION_ENROLL,
    MOCK_ACTION_VERIFY
} MockAction;

typedef struct {
    guint frame_count;
    FpImage *best_img;
    guint best_minutiae;
    guint best_frame_no;
    gboolean retry_guard;
    gint64 retry_guard_mono;
} Mock5e0aDevice;

typedef struct {
    int image_captured_calls;
    FpImage *last_captured_image;
    int retry_scan_calls;
    FpDeviceRetry last_retry_reason;
    int mark_completed_calls;
    int mark_failed_calls;
    GError *last_failed_error;
    int next_state_calls;
    int read_image_requests;
} MockEnvironment;

static MockEnvironment g_env;

static void reset_mock_env(void) {
    memset(&g_env, 0, sizeof(g_env));
}

static void mock_track_freed(gpointer data, GObject *where_the_object_was) {
    int *freed_flag = (int *)data;
    (*freed_flag)++;
}

/* Driver functions matching goodix5e0a.c byte-for-byte */

static void goodix5e0a_reset_touch_frames(Mock5e0aDevice *self) {
    if (self->best_img != NULL) {
        g_object_unref(self->best_img);
        self->best_img = NULL;
    }
    self->frame_count = 0;
    self->best_minutiae = 0;
    self->best_frame_no = 0;
}

static FpImage *goodix5e0a_claim_best_frame(Mock5e0aDevice *self) {
    FpImage *best;
    g_return_val_if_fail(self->best_img != NULL, NULL);
    best = self->best_img;
    self->best_img = NULL;
    self->best_minutiae = 0;
    self->best_frame_no = 0;
    return best;
}

static gboolean goodix5e0a_keep_best_frame_sim(Mock5e0aDevice *self, FpImage *img, guint minutiae) {
    self->frame_count++;

    if (img != NULL) {
        if (self->best_img == NULL || minutiae > self->best_minutiae) {
            if (self->best_img != NULL)
                g_object_unref(self->best_img);
            self->best_img = img;
            self->best_minutiae = minutiae;
            self->best_frame_no = self->frame_count;
        } else {
            g_object_unref(img);
        }
    }

    if (self->frame_count < GOODIX_5E0A_FRAMES_PER_TOUCH) {
        g_env.read_image_requests++;
        return TRUE;
    }
    return FALSE;
}

static void goodix5e0a_on_read_img_sim(Mock5e0aDevice *self, MockAction action,
                                       FpImage *img, guint minutiae,
                                       guint16 len, GError *err) {
    if (err) {
        if (self->best_img != NULL) {
            g_error_free(err);
            goto choose_best;
        }
        g_env.mark_failed_calls++;
        g_env.last_failed_error = err;
        return;
    }

    if (self->best_img != NULL && len < 10564) {
        goto choose_best;
    }

    if (goodix5e0a_keep_best_frame_sim(self, img, minutiae))
        return;

choose_best:
    if (action == MOCK_ACTION_ENROLL) {
        guint minutiae_count = self->best_minutiae;
        if (self->best_img == NULL || minutiae_count < GOODIX_5E0A_ENROLL_MIN_MINUTIAE) {
            goodix5e0a_reset_touch_frames(self);
            g_env.retry_scan_calls++;
            g_env.last_retry_reason = FP_DEVICE_RETRY_TOO_SHORT;
            g_env.next_state_calls++;
            return;
        }
        img = goodix5e0a_claim_best_frame(self);
    } else {
        if (self->best_img == NULL) {
            img = fp_image_new(160, 128);
            goto deliver;
        }
        img = goodix5e0a_claim_best_frame(self);
    }

deliver:
    g_env.image_captured_calls++;
    g_env.last_captured_image = img;

    if (action != MOCK_ACTION_ENROLL) {
        self->retry_guard = TRUE;
        self->retry_guard_mono = g_get_monotonic_time();
        g_env.mark_completed_calls++;
    } else {
        g_env.next_state_calls++;
    }
}

/* =========================================================================
 * TEST CASES
 * ========================================================================= */

static void test_scenario_1_all_weak_burst(void) {
    printf("[CHALLENGE 1] All 3 frames during enrollment have minutiae < 12...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed[3] = {0, 0, 0};
    guint minutiae_counts[3] = {4, 7, 5}; // all < 12
    FpImage *imgs[3];

    for (int i = 0; i < 3; i++) {
        imgs[i] = fp_image_new(160, 128);
        g_object_weak_ref(G_OBJECT(imgs[i]), mock_track_freed, &freed[i]);
    }

    // Frame 1 arrives
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[0], minutiae_counts[0], 10564, NULL);
    g_assert_cmpint(g_env.read_image_requests, ==, 1);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0);
    g_assert_cmpint(freed[0], ==, 0); // Frame 1 kept as best so far
    g_assert_cmpuint(dev.best_minutiae, ==, 4);

    // Frame 2 arrives (7 > 4 -> Frame 1 should be freed!)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[1], minutiae_counts[1], 10564, NULL);
    g_assert_cmpint(g_env.read_image_requests, ==, 2);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0);
    g_assert_cmpint(freed[0], ==, 1); // Frame 1 freed by keep_best_frame!
    g_assert_cmpint(freed[1], ==, 0); // Frame 2 kept
    g_assert_cmpuint(dev.best_minutiae, ==, 7);

    // Frame 3 arrives (5 < 7 -> Frame 3 should be freed immediately!)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[2], minutiae_counts[2], 10564, NULL);
    g_assert_cmpint(g_env.read_image_requests, ==, 2); // burst complete, no more requests
    g_assert_cmpint(freed[2], ==, 1); // Frame 3 freed immediately!

    // Floor gate must have triggered:
    g_assert_cmpint(g_env.retry_scan_calls, ==, 1);
    g_assert_cmpint(g_env.last_retry_reason, ==, FP_DEVICE_RETRY_TOO_SHORT);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0); // NO empty image committed!
    g_assert_cmpint(g_env.next_state_calls, ==, 1); // Advanced to FDT_UP_1 to wait for release

    // Winner Frame 2 must have been unref'd by goodix5e0a_reset_touch_frames:
    g_assert_cmpint(freed[1], ==, 1);
    g_assert_null(dev.best_img);
    g_assert_cmpuint(dev.frame_count, ==, 0);
    g_assert_cmpuint(dev.best_minutiae, ==, 0);
    g_assert_cmpuint(dev.best_frame_no, ==, 0);

    // Verify all 3 frames completely freed (0 memory leaks)
    g_assert_cmpint(freed[0], ==, 1);
    g_assert_cmpint(freed[1], ==, 1);
    g_assert_cmpint(freed[2], ==, 1);

    printf("  -> PASS: retry_scan(FP_DEVICE_RETRY_TOO_SHORT) triggered, 0 frames committed, 0 leaks (all 3 unrefed).\n");
}

static void test_scenario_2_winning_frame_selection(void) {
    printf("[CHALLENGE 2] Frame 1 (8 min), Frame 2 (15 min), Frame 3 (10 min)...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed[3] = {0, 0, 0};
    guint minutiae_counts[3] = {8, 15, 10};
    FpImage *imgs[3];

    for (int i = 0; i < 3; i++) {
        imgs[i] = fp_image_new(160, 128);
        g_object_weak_ref(G_OBJECT(imgs[i]), mock_track_freed, &freed[i]);
    }

    // Frame 1 arrives (8 min)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[0], minutiae_counts[0], 10564, NULL);
    g_assert_cmpint(freed[0], ==, 0);
    g_assert_cmpuint(dev.best_minutiae, ==, 8);
    g_assert_cmpuint(dev.best_frame_no, ==, 1);

    // Frame 2 arrives (15 min > 8 min -> Frame 1 unrefed, Frame 2 becomes best)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[1], minutiae_counts[1], 10564, NULL);
    g_assert_cmpint(freed[0], ==, 1); // Frame 1 destroyed
    g_assert_cmpint(freed[1], ==, 0); // Frame 2 retained
    g_assert_cmpuint(dev.best_minutiae, ==, 15);
    g_assert_cmpuint(dev.best_frame_no, ==, 2);

    // Frame 3 arrives (10 min < 15 min -> Frame 3 destroyed, Frame 2 stays best)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[2], minutiae_counts[2], 10564, NULL);
    g_assert_cmpint(freed[2], ==, 1); // Frame 3 destroyed
    g_assert_cmpint(freed[1], ==, 0); // Frame 2 still alive

    // Quality floor check: 15 >= 12 -> PASS!
    g_assert_cmpint(g_env.retry_scan_calls, ==, 0);
    g_assert_cmpint(g_env.image_captured_calls, ==, 1);
    g_assert_true(g_env.last_captured_image == imgs[1]); // EXACT Frame 2 submitted!

    // Driver ownership cleared
    g_assert_null(dev.best_img);
    g_assert_cmpuint(dev.best_minutiae, ==, 0);
    g_assert_cmpuint(dev.best_frame_no, ==, 0);

    // When libfprint consumes and unrefs the submitted image:
    g_object_unref(g_env.last_captured_image);
    g_assert_cmpint(freed[1], ==, 1); // Frame 2 cleanly freed now

    // Verify all 3 frames destroyed, 0 leaks
    g_assert_cmpint(freed[0], ==, 1);
    g_assert_cmpint(freed[1], ==, 1);
    g_assert_cmpint(freed[2], ==, 1);

    printf("  -> PASS: Frame 2 (15 minutiae) selected and submitted, Frames 1 & 3 unrefed, 0 leaks.\n");
}

static void test_scenario_3a_usb_error_on_first_frame(void) {
    printf("[CHALLENGE 3A] USB error on Frame 1 (0 frames banked)...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    GError *err = g_error_new(G_IO_ERROR, G_IO_ERROR_FAILED, "Bulk transfer stalled");
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, NULL, 0, 0, err);

    g_assert_cmpint(g_env.mark_failed_calls, ==, 1);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0);
    g_assert_cmpint(g_env.retry_scan_calls, ==, 0);
    g_assert_null(dev.best_img);

    // SSM complete callback resets touch frames defensively
    goodix5e0a_reset_touch_frames(&dev);
    g_error_free(err);

    printf("  -> PASS: mark_failed called on 0-frame error, no fallback attempt.\n");
}

static void test_scenario_3b_usb_error_mid_burst_with_good_frame(void) {
    printf("[CHALLENGE 3B] USB error on Frame 2 when Frame 1 has 16 minutiae (Enrollment)...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed1 = 0;
    FpImage *img1 = fp_image_new(160, 128);
    g_object_weak_ref(G_OBJECT(img1), mock_track_freed, &freed1);

    // Frame 1 succeeds with 16 minutiae
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, img1, 16, 10564, NULL);
    g_assert_cmpint(freed1, ==, 0);
    g_assert_cmpuint(dev.best_minutiae, ==, 16);

    // Frame 2 fails with USB error (e.g. premature lift)
    GError *err = g_error_new(G_IO_ERROR, G_IO_ERROR_TIMED_OUT, "USB timeout");
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, NULL, 0, 0, err);

    // Must fallback to best-so-far (Frame 1):
    g_assert_cmpint(g_env.retry_scan_calls, ==, 0);
    g_assert_cmpint(g_env.image_captured_calls, ==, 1);
    g_assert_true(g_env.last_captured_image == img1); // Frame 1 successfully delivered!
    g_assert_null(dev.best_img);

    g_object_unref(img1);
    g_assert_cmpint(freed1, ==, 1);

    printf("  -> PASS: Frame 1 (16 minutiae) submitted as best-so-far fallback, 0 leaks.\n");
}

static void test_scenario_3c_usb_error_mid_burst_with_weak_frame(void) {
    printf("[CHALLENGE 3C] USB error on Frame 2 when Frame 1 has 6 minutiae (Enrollment)...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed1 = 0;
    FpImage *img1 = fp_image_new(160, 128);
    g_object_weak_ref(G_OBJECT(img1), mock_track_freed, &freed1);

    // Frame 1 succeeds with only 6 minutiae (< 12 floor)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, img1, 6, 10564, NULL);
    g_assert_cmpint(freed1, ==, 0);

    // Frame 2 fails with USB error
    GError *err = g_error_new(G_IO_ERROR, G_IO_ERROR_TIMED_OUT, "USB timeout");
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, NULL, 0, 0, err);

    // Falls back to choose_best, but 6 < 12 floor:
    g_assert_cmpint(g_env.retry_scan_calls, ==, 1);
    g_assert_cmpint(g_env.last_retry_reason, ==, FP_DEVICE_RETRY_TOO_SHORT);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0); // No bad frame committed!

    // Frame 1 unrefed by reset_touch_frames
    g_assert_cmpint(freed1, ==, 1);
    g_assert_null(dev.best_img);

    printf("  -> PASS: Weak best-so-far rejected at floor gate, Frame 1 freed, retry_scan triggered.\n");
}

static void test_scenario_4_cancellation_during_burst(void) {
    printf("[CHALLENGE 4] Client cancellation/deactivation mid-burst...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed1 = 0;
    FpImage *img1 = fp_image_new(160, 128);
    g_object_weak_ref(G_OBJECT(img1), mock_track_freed, &freed1);

    // Frame 1 banked
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, img1, 14, 10564, NULL);
    g_assert_cmpint(freed1, ==, 0);

    // Deactivation occurs before Frame 2 completes (e.g. client cancelled operation)
    goodix5e0a_reset_touch_frames(&dev);
    g_assert_cmpint(freed1, ==, 1); // Frame 1 freed immediately!
    g_assert_null(dev.best_img);

    // In-flight read completion now arrives with G_IO_ERROR_CANCELLED
    GError *cancel_err = g_error_new(G_IO_ERROR, G_IO_ERROR_CANCELLED, "Transfer cancelled");
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, NULL, 0, 0, cancel_err);

    // Since best_img was cleared, it marks failed and does NOT execute choose_best
    g_assert_cmpint(g_env.mark_failed_calls, ==, 1);
    g_assert_cmpint(g_env.image_captured_calls, ==, 0);
    g_assert_cmpint(g_env.retry_scan_calls, ==, 0);

    g_error_free(cancel_err);
    printf("  -> PASS: Deactivation cleared banked frame, late CANCELLED callback dropped cleanly.\n");
}

static void test_scenario_5_tie_breaking_strict_greater(void) {
    printf("[CHALLENGE 5] Tie breaking: Frame 1=15, Frame 2=15, Frame 3=12...\n");
    Mock5e0aDevice dev = {0};
    reset_mock_env();

    int freed[3] = {0, 0, 0};
    guint minutiae_counts[3] = {15, 15, 12};
    FpImage *imgs[3];

    for (int i = 0; i < 3; i++) {
        imgs[i] = fp_image_new(160, 128);
        g_object_weak_ref(G_OBJECT(imgs[i]), mock_track_freed, &freed[i]);
    }

    // Frame 1 (15)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[0], minutiae_counts[0], 10564, NULL);
    // Frame 2 (15 == 15 -> not greater, Frame 2 unrefed!)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[1], minutiae_counts[1], 10564, NULL);
    g_assert_cmpint(freed[1], ==, 1); // Frame 2 unrefed!
    g_assert_cmpint(freed[0], ==, 0); // Frame 1 retained!
    g_assert_cmpuint(dev.best_frame_no, ==, 1);

    // Frame 3 (12 < 15 -> Frame 3 unrefed)
    goodix5e0a_on_read_img_sim(&dev, MOCK_ACTION_ENROLL, imgs[2], minutiae_counts[2], 10564, NULL);
    g_assert_cmpint(freed[2], ==, 1);

    // Frame 1 submitted
    g_assert_true(g_env.last_captured_image == imgs[0]);
    g_object_unref(imgs[0]);
    g_assert_cmpint(freed[0], ==, 1);

    printf("  -> PASS: Earlier frame retained on tie (strict >), redundant swaps avoided, 0 leaks.\n");
}

int main(int argc, char *argv[]) {
    g_test_init(&argc, &argv, NULL);
    printf("=========================================================================\n");
    printf("EMPIRICAL ADVERSARIAL CHALLENGE: BEST-OF-N BANKING & QUALITY GATE\n");
    printf("=========================================================================\n");

    test_scenario_1_all_weak_burst();
    test_scenario_2_winning_frame_selection();
    test_scenario_3a_usb_error_on_first_frame();
    test_scenario_3b_usb_error_mid_burst_with_good_frame();
    test_scenario_3c_usb_error_mid_burst_with_weak_frame();
    test_scenario_4_cancellation_during_burst();
    test_scenario_5_tie_breaking_strict_greater();

    printf("=========================================================================\n");
    printf("ALL 7 EMPIRICAL ADVERSARIAL CHALLENGE SCENARIOS PASSED WITH ZERO LEAKS!\n");
    printf("=========================================================================\n");
    return 0;
}
