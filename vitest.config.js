import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['the_flip/static/**/*.test.js'],
  },
});
