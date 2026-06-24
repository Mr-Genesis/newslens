import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.newslens.app',
  appName: 'NewsLens',
  webDir: 'out',
  plugins: {
    FirebaseAuthentication: {
      skipNativeAuth: false, // run the REAL native Google flow, then bridge into the JS SDK
      providers: ['google.com'],
    },
  },
};

export default config;
