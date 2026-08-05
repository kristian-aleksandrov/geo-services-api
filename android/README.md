# GeoHut Maps — Android Wrapper

A minimal Android WebView wrapper around [maps.geohut.eu](https://maps.geohut.eu/) (a NextGIS Web GIS instance), packaged as a standalone APK.

## What it does

- Loads `https://maps.geohut.eu/` in a full-screen WebView.
- Keeps navigation within the `geohut.eu` domain in-app; other links (e.g. login redirects, external help links) open in the system browser.
- Supports pull-to-refresh, in-app back navigation, JS/DOM storage (required by the NextGIS Web frontend), file uploads, downloads, and browser geolocation (for map "locate me" controls), with runtime permission prompts.
- Shows a friendly retry screen when offline or on load failure.

It is a thin client only — all map data, auth, and rendering are served by `maps.geohut.eu`; this project owns no backend logic.

## Project layout

```
android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/eu/geohut/maps/MainActivity.kt
│       └── res/
├── build.gradle.kts
├── settings.gradle.kts
└── keystore.properties        # untracked — see "Release signing" below
```

## Building

Requires JDK 17+ and the Android SDK (`platform-tools`, `platforms;android-34`, `build-tools;34.0.0`).

```bash
export ANDROID_HOME=/path/to/android-sdk
echo "sdk.dir=$ANDROID_HOME" > local.properties   # first time only

./gradlew assembleDebug     # unsigned-for-dev, debug-keystore signed APK
./gradlew assembleRelease   # release build (unsigned unless keystore.properties is set up)
```

Debug APK output: `app/build/outputs/apk/debug/app-debug.apk`
Release APK output: `app/build/outputs/apk/release/app-release.apk`

### Release signing

`keystore.properties` is gitignored since it holds signing credentials. To produce a signed release build, create your own keystore and file:

```bash
keytool -genkeypair -v -keystore keystore/release.keystore -alias geohutmaps \
  -keyalg RSA -keysize 2048 -validity 10000
```

```properties
# android/keystore.properties
storeFile=keystore/release.keystore
storePassword=...
keyAlias=geohutmaps
keyPassword=...
```

Without this file, `assembleRelease` still succeeds but produces an unsigned APK.

## Installing

Sideload with adb:

```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

Or transfer the APK to a device and install directly (enable "install from unknown sources" for the file manager/browser used).

## Notes

- `minSdk = 26` (Android 8.0+) — lets the app ship a vector-only adaptive launcher icon with no raster fallback assets.
- Login state and any GIS session cookies persist in the WebView's storage between app launches, same as a browser tab would.
