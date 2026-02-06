import { writable } from 'svelte/store';
import type { Me } from '$lib/api';

export const meStore = writable<Me | null>(null);
