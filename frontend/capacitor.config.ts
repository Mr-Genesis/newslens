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
    SplashScreen: {
      // Hold the native splash until the web app paints, then fade it out — a
      // controlled hand-off into the WebView instead of a hard cut. The app
      // calls SplashScreen.hide() once the overlay is on screen (SplashScreen.tsx).
      launchAutoHide: false,
      backgroundColor: '#0C0C0E',
      androidSplashResourceName: 'splash',
      androidScaleType: 'CENTER_CROP',
      splashFullScreen: true,
      splashImmersive: true,
    },
  },
};

export default config;
