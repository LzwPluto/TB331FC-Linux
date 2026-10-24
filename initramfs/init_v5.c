#define _GNU_SOURCE
/*
 * init v5 for TB331FC mainline bring-up.
 *  - mounts pseudo filesystems
 *  - stages busybox from the initramfs (or an SD card if present)
 *  - attaches to /dev/console so the shell gets a controlling tty
 *  - runs /diag.sh automatically (no keyboard needed to see results)
 *  - then drops to an interactive shell
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/sysinfo.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef TIOCSCTTY
#define TIOCSCTTY 0x540E
#endif

static int copy_file(const char *src, const char *dst)
{
    int in = open(src, O_RDONLY);
    if (in < 0) return -1;
    int out = open(dst, O_WRONLY | O_CREAT | O_TRUNC, 0755);
    if (out < 0) { close(in); return -1; }
    char buf[65536];
    ssize_t n;
    while ((n = read(in, buf, sizeof buf)) > 0) {
        ssize_t w = 0;
        while (w < n) {
            ssize_t r = write(out, buf + w, (size_t)(n - w));
            if (r <= 0) { close(in); close(out); return -1; }
            w += r;
        }
    }
    close(in);
    close(out);
    chmod(dst, 0755);
    return 0;
}


/* mount via busybox: the direct mount(2) call returns EFAULT on this kernel
 * while `busybox mount` works, so shell out to it. */
static int sh_mount(const char *dev, const char *type)
{
	pid_t p = fork();
	int st = 0;

	if (p == 0) {
		if (type) {
			char *const av[] = { "/bin/busybox", "mount", "-t",
					     (char *)type, (char *)dev, "/mnt", NULL };
			execv("/bin/busybox", av);
		} else {
			char *const av[] = { "/bin/busybox", "mount",
					     (char *)dev, "/mnt", NULL };
			execv("/bin/busybox", av);
		}
		_exit(127);
	}
	if (p < 0)
		return -1;
	waitpid(p, &st, 0);
	return (WIFEXITED(st) && WEXITSTATUS(st) == 0) ? 0 : -1;
}

static void attach_console(void)
{
    int fd = open("/dev/console", O_RDWR);
    if (fd < 0) return;
    setsid();
    ioctl(fd, TIOCSCTTY, 0);
    dup2(fd, 0);
    dup2(fd, 1);
    dup2(fd, 2);
    if (fd > 2) close(fd);
}

/* ---------------------------------------------------------------------------
 * Filesystem-free script extraction.
 *
 * mount() on this kernel returns EFAULT for the SD partition, so instead of
 * relying on any filesystem driver we scan the raw block device for a marker
 * pair and pull the script out. A freshly formatted card stores small files in
 * low clusters, so the first few tens of MB are enough.
 * ------------------------------------------------------------------------- */
#define SCAN_CHUNK   (1u << 20)          /* 1 MiB */
#define SCAN_MAX     (64u << 20)         /* 64 MiB */
#define MARK_BEGIN   "TB331FC-SCRIPT-BEGIN"
#define MARK_END     "TB331FC-SCRIPT-END"

static int extract_marked_script(const char *dev, const char *out)
{
    int fd = open(dev, O_RDONLY);
    if (fd < 0) {
        printf("[init] raw scan: cannot open %s\n", dev);
        return -1;
    }

    unsigned char *buf = malloc(SCAN_CHUNK + 4096);
    if (!buf) { close(fd); return -1; }

    unsigned long off = 0;
    ssize_t keep = 0;           /* bytes carried over from previous chunk */
    int found = 0;
    FILE *of = NULL;

    while (off < SCAN_MAX) {
        ssize_t n = read(fd, buf + keep, SCAN_CHUNK);
        if (n <= 0) break;
        ssize_t total = keep + n;

        if (!found) {
            unsigned char *p = memmem(buf, (size_t)total, MARK_BEGIN, strlen(MARK_BEGIN));
            if (p) {
                found = 1;
                of = fopen(out, "wb");
                if (!of) break;
                /* start of the script is the beginning of the next line */
                unsigned char *q = memchr(p, '\n', (size_t)(buf + total - p));
                if (!q) q = p + strlen(MARK_BEGIN) - 1;
                else q++;
                /* copy whatever we already have of the payload */
                ssize_t len = (ssize_t)(buf + total - q);
                if (len > 0) {
                    unsigned char *e = memmem(q, (size_t)len, MARK_END, strlen(MARK_END));
                    if (e) {
                        fwrite(q, 1, (size_t)(e - q), of);
                        fclose(of); of = NULL; close(fd); free(buf);
                        chmod(out, 0755);
                        printf("[init] raw scan: script found at offset ~%lu\n", off);
                        return 0;
                    }
                    fwrite(q, 1, (size_t)len, of);
                }
            }
        } else if (of) {
            unsigned char *e = memmem(buf, (size_t)total, MARK_END, strlen(MARK_END));
            if (e) {
                fwrite(buf, 1, (size_t)(e - buf), of);
                fclose(of); of = NULL; close(fd); free(buf);
                chmod(out, 0755);
                printf("[init] raw scan: script found\n");
                return 0;
            }
            fwrite(buf, 1, (size_t)total, of);
        }

        off += (unsigned long)n;
        /* keep a tail so a marker split across chunks is still found */
        keep = (ssize_t)(strlen(MARK_BEGIN) + 4);
        if (total > keep) {
            memmove(buf, buf + total - keep, (size_t)keep);
        } else {
            keep = total;
        }
    }

    if (of) fclose(of);
    close(fd);
    free(buf);
    printf("[init] raw scan: marker not found in first %u MiB\n", SCAN_MAX >> 20);
    return -1;
}

static const char *CANDS[] = { "/dev/mmcblk0p1", "/dev/mmcblk1p1", NULL };
static const char *TYPES[] = { "vfat", "ext4", NULL };

int main(void)
{
    mkdir("/proc", 0755); mkdir("/sys", 0755); mkdir("/dev", 0755);
    mkdir("/tmp", 0755);  mkdir("/mnt", 0755);
    mount("proc", "/proc", "proc", 0, NULL);
    mount("sysfs", "/sys", "sysfs", 0, NULL);
    mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);
    mount("tmpfs", "/tmp", "tmpfs", 0, NULL);

    struct utsname u;
    uname(&u);
    struct sysinfo si;
    sysinfo(&si);

    printf("\n\n=============================================\n");
    printf("  Lenovo TB331FC  --  MAINLINE LINUX  UP\n");
    printf("  kernel : %s\n", u.release);
    printf("  memory : %lu MB free / %lu MB\n",
           si.freeram * si.mem_unit / 1048576UL,
           si.totalram * si.mem_unit / 1048576UL);
    printf("  cpus   : %ld online\n", sysconf(_SC_NPROCESSORS_ONLN));
    printf("=============================================\n\n");

    mkdir("/bin", 0755);
    if (access("/bin/busybox", F_OK) != 0 && copy_file("/busybox", "/bin/busybox") != 0)
        printf("[init] WARN: cannot stage busybox\n");
    chmod("/bin/busybox", 0755);

	/* early gadget bring-up: the serial console must exist before the
	 * switchroot to Alpine, otherwise we lose it. */
	if (access("/gadget.sh", R_OK) == 0) {
		pid_t gp = fork();
		if (gp == 0) {
			char *const ga[] = { "/bin/busybox", "sh", "/gadget.sh", NULL };
			execv("/bin/busybox", ga);
			_exit(127);
		}
		if (gp > 0) { int st; waitpid(gp, &st, 0); }
	}

    int card_mounted = 0;
    int last_errno = 0;
    const char *last_dev = NULL;
    /* The SD card is usually probed a moment AFTER /init starts, so poll for
     * it instead of trying once. */
    for (int attempt = 0; attempt < 20 && !card_mounted; attempt++) {
        for (int c = 0; CANDS[c] && !card_mounted; c++) {
            if (access(CANDS[c], F_OK) != 0) continue;
            for (int t = 0; TYPES[t]; t++) {
                if (sh_mount(CANDS[c], TYPES[t]) == 0) {
                    card_mounted = 1;
                    printf("[init] SD card mounted: %s (%s) after %ds\n",
                           CANDS[c], TYPES[t], attempt);
                    if (access("/mnt/busybox", F_OK) == 0)
                        copy_file("/mnt/busybox", "/bin/busybox");
                    break;
                }
                last_errno = errno;
                last_dev = CANDS[c];
            }
            /* last resort: let the kernel autodetect the filesystem */
            if (!card_mounted && sh_mount(CANDS[c], NULL) == 0) {
                card_mounted = 1;
                printf("[init] SD card mounted: %s (autodetect) after %ds\n",
                       CANDS[c], attempt);
                if (access("/mnt/busybox", F_OK) == 0)
                    copy_file("/mnt/busybox", "/bin/busybox");
            }
        }
        if (!card_mounted)
            sleep(1);
    }
    if (!card_mounted) {
        printf("[init] no SD card mounted (waited 20s)\n");
        if (last_dev)
            printf("[init] last mount attempt: %s errno=%d (%s)\n",
                   last_dev, last_errno, strerror(last_errno));
        else
            printf("[init] no candidate device ever appeared\n");
        for (int c = 0; CANDS[c]; c++)
            printf("[init]   %s -> %s\n", CANDS[c],
                   access(CANDS[c], F_OK) == 0 ? "exists" : "absent");
    }

    /* If the SD card carries an ext4 rootfs image, hand over to it.  exec
     * keeps us as PID 1, which busybox switch_root requires. */
    if (card_mounted && access("/mnt/alpine-rootfs.img", R_OK) == 0) {
        printf("\n[init] found /mnt/alpine-rootfs.img -> switching root\n");
        fflush(stdout);
        char *const sv[] = { "/bin/busybox", "sh", "/switchroot.sh", NULL };
        execv("/bin/busybox", sv);
        printf("[init] exec switchroot.sh failed\n");
    }

    /* If the kernel cannot mount the partition, pull the script out of the raw
     * block device instead (mount() gives EFAULT on this kernel). */
    int have_raw_script = 0;
    if (!card_mounted) {
        printf("[init] mount failed, trying raw scan of /dev/mmcblk0 ...\n");
        if (extract_marked_script("/dev/mmcblk0", "/tmp/run.sh") == 0)
            have_raw_script = 1;
    }

    if (access("/bin/busybox", X_OK) != 0) {
        printf("[init] no busybox - heartbeat only\n");
        for (int i = 1;; i++) { printf("[init] alive #%d\n", i); fflush(stdout); sleep(5); }
    }

    attach_console();
    setenv("PATH", "/bin:/sbin:/usr/bin:/usr/sbin:/tmp", 1);
    setenv("HOME", "/", 1);
    setenv("TERM", "linux", 1);
    setenv("PS1", "tb331fc# ", 1);

    /* ---- USB CDC-ACM serial gadget: gives us a real terminal over USB-C ---- */
    if (access("/gadget.sh", R_OK) == 0) {
        printf("\n[init] setting up USB serial gadget...\n");
        fflush(stdout);
        pid_t gp = fork();
        if (gp == 0) {
            char *const ga[] = { "/bin/busybox", "sh", "/gadget.sh", NULL };
            execv("/bin/busybox", ga);
            _exit(127);
        }
        if (gp > 0) { int st; waitpid(gp, &st, 0); }

        if (access("/dev/ttyGS0", F_OK) == 0) {
            printf("[init] /dev/ttyGS0 present, spawning shell on it\n");
            fflush(stdout);
            gp = fork();
            if (gp == 0) {
                int fd = open("/dev/ttyGS0", O_RDWR);
                if (fd >= 0) {
                    setsid();
                    ioctl(fd, TIOCSCTTY, 0);
                    dup2(fd, 0);
                    dup2(fd, 1);
                    dup2(fd, 2);
                    if (fd > 2) close(fd);
                    setenv("PATH", "/bin:/sbin:/usr/bin:/usr/sbin:/tmp", 1);
                    setenv("HOME", "/", 1);
                    setenv("TERM", "vt100", 1);
                    setenv("PS1", "tb331fc-usb# ", 1);
                    char *const av2[] = { "/bin/busybox", "sh", NULL };
                    execv("/bin/busybox", av2);
                }
                _exit(127);
            }
            if (gp > 0)
                printf("[init] USB serial shell running (pid %d)\n", (int)gp);
        } else {
            printf("[init] /dev/ttyGS0 NOT present - gadget failed\n");
        }
    }

    /* If the SD card carries run.sh, run that instead of the built-in diag.
     * This lets us iterate on the device without reflashing anything. */
    const char *script = NULL;
    if (card_mounted && access("/mnt/run.sh", R_OK) == 0)
        script = "/mnt/run.sh";
    else if (have_raw_script && access("/tmp/run.sh", R_OK) == 0)
        script = "/tmp/run.sh";
    else if (access("/diag.sh", R_OK) == 0)
        script = "/diag.sh";

    if (script) {
        printf("\n[init] running %s\n\n", script);
        fflush(stdout);
        pid_t p = fork();
        if (p == 0) {
            char *const dv[] = { "/bin/busybox", "sh", (char *)script, NULL };
            execv("/bin/busybox", dv);
            _exit(127);
        }
        if (p > 0) { int st; waitpid(p, &st, 0); }
    }

    /* Keep re-printing the summary so it is always the last thing on screen:
     * there is no keyboard, so an interactive prompt is not very useful anyway. */
    for (int i = 1;; i++) {
        printf("\n[init] ===== status #%d =====\n", i);
        printf("[init] SD mounted : %s\n", card_mounted ? "YES" : "NO");
        printf("[init] mount errno: %d (%s)\n", last_errno,
               last_errno ? strerror(last_errno) : "n/a");
        for (int c = 0; CANDS[c]; c++)
            printf("[init]   %s -> %s\n", CANDS[c],
                   access(CANDS[c], F_OK) == 0 ? "exists" : "absent");
        printf("[init] script     : %s\n", script ? script : "(none)");
        printf("[init] =====================\n");
        fflush(stdout);
        sleep(5);
    }
    return 0;
}
