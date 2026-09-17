# SELinux policy for the Goodix engine loader

On SELinux-enforcing distros (Fedora, RHEL, openSUSE with SELinux), stock
policy denies `fprintd` permission to write into the anonymous memfd the
driver uses to load `GoodixEngineAdapter.dll` in-process. Enrollment then
fails with `failed to load GoodixEngineAdapter.dll` / `Failed to start Milan
enrollment context` even though the DLL is readable. `journalctl -b 0
--grep="AVC|denied"` shows the real cause: `denied { write } ... memfd:goodix_engine`.

The rule in `goodix-engine.te` is the minimal allow needed for the loader's
memfd path. It grants `fprintd_t` access only to `tmpfs_t` files (memfd), not
to the filesystem, and does not disable SELinux or add broad exceptions.

Apply it (root, on the target machine):

```sh
checkmodule -M -m -o goodix-engine.mod goodix-engine.te
semodule_package -o goodix-engine.pp -m goodix-engine.mod
sudo semodule -i goodix-engine.pp
```

Then restart fprintd (`sudo systemctl restart fprintd`) and retry
`fprintd-enroll`. If new AVCs appear for a different permission or class,
do not widen this file on guesswork; reproduce first and derive the rule
from your own audit log.

Remove: `sudo semodule -r goodix-engine`. NixOS does not ship SELinux; the
NixOS module path does not need this.
