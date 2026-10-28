/*
 * OnePlus Ace 3 / aston Synaptics S3910 touch screen.
 *
 * Boot argument aston_touch=1 opts in.  The controller is brought up over a
 * polled bit-bang SPI and its reports are pushed into the kernel's touch queue
 * (/dev/hakios-touch, bsd/dev/hakios.input.c), which is what backboardd turns
 * into HID events for the window server.
 *
 * Wiring (live aston device tree, tp/aston-oplus_tp-23801.dtsi):
 *   QUPV3_SE4: MISO gpio44, MOSI gpio45, CLK gpio46, CS gpio47
 *   INT gpio25 (active low), RESET gpio24, AVDD enable gpio10, VDD_IO = L4B
 *
 * Nothing is written to the controller's nonvolatile memory: only a volatile
 * report layout is configured, exactly as on dodge and giulia.
 */
#include <kern/clock.h>
#include <kern/thread.h>
#include <libkern/libkern.h>
#include <mach/mach_types.h>
#include <pexpert/pexpert.h>
#include <sys/hakios.input.h>
#include <sys/systm.h>

extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
extern kern_return_t thread_terminate(thread_t);

static uint32_t aston_touch_arg(const char *name, uint32_t dflt);

static uint32_t
s39_rd(uintptr_t a)
{
	return *(volatile uint32_t *)a;
}

static void
s39_wr(uintptr_t a, uint32_t v)
{
	*(volatile uint32_t *)a = v;
	__asm__ volatile("dsb sy" ::: "memory");
}

static void
s39_delay(unsigned us)
{
	delay_for_interval(us, NSEC_PER_USEC);
}

#include "hakios.aston_touch_hw.h"

struct s39_contact {
	uint32_t x, y;
};

/* Decoder for the volatile report layout configured above. */
static int
s39_decode(const uint8_t *p, unsigned n, unsigned max_x, unsigned max_y,
    struct s39_contact contact[10], unsigned *mask)
{
	if (!n || p[0] > 10 || n != 1u + 5u * p[0] || !max_x || !max_y) return -1;
	unsigned seen = 0, active = 0;
	for (unsigned i = 0; i < p[0]; i++) {
		const uint8_t *q = p + 1 + 5 * i;
		unsigned id = q[0] & 15, kind = q[0] >> 4;
		unsigned x = q[1] | q[2] << 8, y = q[3] | q[4] << 8;
		if (id >= 10 || (seen & (1u << id)) || x > max_x || y > max_y) return -1;
		seen |= 1u << id;
		if (kind != 1 && kind != 2) continue;
		contact[id].x = (uint32_t)x * 65535 / max_x;
		contact[id].y = (uint32_t)y * 65535 / max_y;
		active |= 1u << id;
	}
	*mask = active;
	return 0;
}

static struct s39_hw hw;
static struct s39_contact last[10];
static unsigned active;

static void
release_all(void)
{
	for (unsigned i = 0; i < 10; i++)
		if (active & (1u << i))
			hakios_touch_post(HAKIOS_TOUCH_UP, i, last[i].x, last[i].y);
	active = 0;
}

static int
s39_probe(struct s39_hw *h)
{
	int rc = s39_read(h);

	if (rc != 0x10 || h->length < 24) return rc < 0 ? rc : -40;
	if (h->data[0] != 1 || h->data[1] != 1 || memcmp(h->data + 2, "S3910", 5)) return -41;
	return 0;
}

static void
s39_touch_thread(__unused void *arg, __unused wait_result_t wait)
{
	struct s39_hw *h = &hw;
	int rc = -1, probe_rc = -1;
	unsigned reports = 0, bad = 0, errors = 0;
	unsigned muxes[2] = { 2, 0 }, tried = 0;

	/*
	 * The kernel console only starts keeping its log when userland's init is up; a driver
	 * that ran during bsd init would say everything into a buffer nobody reads back. Wait
	 * for init, then work: the log of this run is what the loader fetches over USB.
	 */
	s39_delay(9000000);
	printf("s3910: thread start (aston_touch arg set)\n");

	h->gpio = ml_io_map(S39_TLMM_PA, 0x100000);
	printf("s3910: tlmm %#llx -> %p\n", (unsigned long long)S39_TLMM_PA, h->gpio);
	if (!h->gpio) goto failed;

	/* AVDD (2.8 V) enable pin, active high. */
	h->mux = muxes[0];
	s39_pin(h, S39_AVDD_PIN, 1, 1);
	s39_delay(200000);

	if (aston_touch_arg("aston_touch_ldo", 0)) {
		h->db = ml_io_map(S39_DB_PA, S39_DB_SIZE);
		h->rsc = ml_io_map(S39_RSC_PA, 0x10000);
		printf("s3910: db %p rsc %p regulator-scan\n", h->db, h->rsc);
		if (h->db && h->rsc) {
			s39_cmddb_dump(h);
			rc = s39_vdd_io(h);
			printf("s3910: vdd_io (L4B) vote rc=%d status=%#x\n", rc, h->last_status);
			if (rc) rc = -10;
		} else {
			rc = -11;
		}
		s39_delay(100000);
	}
	/* A successful rail vote leaves rc == 0; that must not be mistaken for a probe result. */
	if (rc) goto failed;

	for (tried = 0; tried < sizeof(muxes) / sizeof(muxes[0]); tried++) {
		h->mux = muxes[tried];
		s39_bus_init(h);
		s39_reset(h);
		probe_rc = s39_probe(h);
		printf("s3910: probe mux=%u rc=%d header=%02x %02x %02x %02x len=%u\n",
		    h->mux, probe_rc, h->header[0], h->header[1], h->header[2], h->header[3], h->length);
		if (probe_rc == 0) break;
	}
	rc = probe_rc;
	if (rc) goto failed;

	printf("s3910: TouchComm v1 application firmware, build=%u\n", s39_le32(h->data + 18));
	rc = s39_start_reports(h);
	if (rc) goto failed;
	printf("s3910: ready; max=%u,%u, 10 contacts, polled SPI\n", h->max_x, h->max_y);

	for (unsigned tick = 0;; tick++) {
		if (!s39_get(h, S39_INT_PIN) || tick % 10 == 0) {
			rc = s39_read(h);
			if (rc < 0) {
				if (++errors >= 10) {
					release_all();
					goto failed;
				}
				bad++;
			} else {
				errors = 0;
				if (rc == 0x11) {
					struct s39_contact point[10] = { { 0 } };
					unsigned mask = 0;
					if (s39_decode(h->data, h->length, h->max_x, h->max_y, point, &mask)) {
						bad++;
						release_all();
					} else {
						for (unsigned i = 0; i < 10; i++) {
							if (mask & (1u << i)) {
								hakios_touch_post(
								    (active & (1u << i)) ? HAKIOS_TOUCH_MOVE : HAKIOS_TOUCH_DOWN,
								    i, point[i].x, point[i].y);
								last[i] = point[i];
							} else if (active & (1u << i)) {
								hakios_touch_post(HAKIOS_TOUCH_UP, i, last[i].x, last[i].y);
							}
						}
						active = mask;
						reports++;
					}
				} else if (rc == 0x10) {
					release_all();
					rc = -42;
					goto failed;
				}
			}
		}
		if (tick % 625 == 0)
			printf("s3910: reports=%u bad=%u active=%#x int=%u\n",
			    reports, bad, active, s39_get(h, S39_INT_PIN));
		s39_delay(8000);
	}

failed:
	printf("s3910: stopped rc=%d setup=%u header=%02x %02x %02x %02x\n", rc, h->setup_step,
	    h->header[0], h->header[1], h->header[2], h->header[3]);
	thread_terminate(current_thread());
}

void
hakios_aston_touch_init(void)
{
	thread_t thread;

	if (!aston_touch_arg("aston_touch", 0)) return;
	if (kernel_thread_start(s39_touch_thread, NULL, &thread) == KERN_SUCCESS)
		thread_deallocate(thread);
}

static uint32_t
aston_touch_arg(const char *name, uint32_t dflt)
{
	uint32_t value = dflt;

	PE_parse_boot_argn(name, &value, sizeof(value));
	return value;
}
