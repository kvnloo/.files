import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	ssr: {
		noExternal: ['@xyflow/svelte', '@xyflow/system'],
	},
	server: {
		proxy: {
			'/api': 'http://localhost:3001',
			'/ws': {
				target: 'ws://localhost:3001',
				ws: true,
			},
		},
	},
});
