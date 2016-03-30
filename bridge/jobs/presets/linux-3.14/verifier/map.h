#ifndef _LDV_MAP_H_
#define _LDV_MAP_H_

/* At the moment maps are represented just as counters, but this won't be the
 * case in future. */

typedef int ldv_map;
typedef void *ldv_map_key;
typedef void *ldv_map_value;

#define ldv_map_init(map) (map = 0)
#define ldv_map_put(map, key, value) (map = value)
#define ldv_map_get(map, key) map
#define ldv_map_contains_key(map, key) (map != 0)
#define ldv_map_remove(map, key) (map = 0)
#define ldv_map_is_empty(map) (map == 0)

#endif /* _LDV_MAP_H_ */
