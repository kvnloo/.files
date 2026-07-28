import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		alias: {
			'$lib': 'src/lib',
			'$lib/*': 'src/lib/*',
			'@aural/shared': '../../packages/shared/src/types',
			'@aural/shared/*': '../../packages/shared/src/*'
		}
	}
};

export default config;
