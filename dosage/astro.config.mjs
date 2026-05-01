// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
  site: "https://henrysck075.github.io",
  base: "/simple_gapi_docs",
	integrations: [
		starlight({
			title: 'the',
			social: [{ icon: 'github', label: 'GitHub', href: 'https://www.touchgrasss.com/' }],
			sidebar: [
				{
					label: 'Reference',
          collapsed: true,
					autogenerate: { directory: 'services' },
				},
			],
		}),
	],
});
