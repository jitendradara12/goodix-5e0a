/* Offline experiment: execute exports through the production Linux PE loader.
 * This translation unit is not linked into or installed as the device driver.
 */
#include "../../libfprint-driver/goodix_milan.c"

int
milan_probe_init (const char *dll_path)
{
  return goodix_milan_init (dll_path) ? 0 : -1;
}

int
milan_probe_call (const char *name, const uint64_t *args, size_t count,
                  uint64_t *result)
{
  typedef uint64_t (MS *ProbeExport) (uint64_t, uint64_t, uint64_t, uint64_t,
                                     uint64_t, uint64_t, uint64_t, uint64_t,
                                     uint64_t, uint64_t, uint64_t);
  uint64_t values[11] = { 0 };
  if (!name || !result || count > 11 || (count && !args))
    return -1;

  g_rec_mutex_lock (&g_milan_mutex);
  if (!g_milan_available)
    {
      g_rec_mutex_unlock (&g_milan_mutex);
      return -2;
    }
  ProbeExport fn = (ProbeExport) get_export (name);
  if (!fn)
    {
      g_rec_mutex_unlock (&g_milan_mutex);
      return -2;
    }
  if (count)
    memcpy (values, args, count * sizeof (uint64_t));
  ensure_gs ();
  *result = fn (values[0], values[1], values[2], values[3], values[4], values[5],
                values[6], values[7], values[8], values[9], values[10]);
  g_rec_mutex_unlock (&g_milan_mutex);
  return 0;
}
