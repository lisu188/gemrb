plugins {
    id("com.android.application")
}

val repoRoot = rootProject.projectDir.resolve("../..").canonicalFile
val depsDir = rootProject.projectDir.resolve(".deps").canonicalFile
val pythonPrefix = depsDir.resolve("python/prefix")
val iconvPrefix = depsDir.resolve("libiconv/prefix")
val sdl2Root = depsDir.resolve("sdl2")
val androidBootstrap = rootProject.projectDir.resolve("cmake/AndroidBootstrap.cmake")

android {
    namespace = "org.gemrb.gemrb"
    compileSdk = 37
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "org.gemrb.gemrb"
        minSdk = 28
        targetSdk = 37
        versionCode = 1
        versionName = "0.9.5-android-dev"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }

        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DCMAKE_PROJECT_TOP_LEVEL_INCLUDES=${androidBootstrap.absolutePath}",
                    "-DGEMRB_ANDROID_SDL2_ROOT=${sdl2Root.absolutePath}",
                    "-DPYTHON_VERSION=3.14",
                    "-DPython_INCLUDE_DIR=${pythonPrefix.resolve("include/python3.14").absolutePath}",
                    "-DPython_LIBRARY=${pythonPrefix.resolve("lib/libpython3.14.so").absolutePath}",
                    "-DIconv_INCLUDE_DIR=${iconvPrefix.resolve("include").absolutePath}",
                    "-DIconv_LIBRARY=${iconvPrefix.resolve("lib/libiconv.a").absolutePath}",
                    "-DGEMRB_ANDROID_ICONV_CHARSET_LIBRARY=${iconvPrefix.resolve("lib/libcharset.a").absolutePath}",
                    "-DSDL_BACKEND=SDL2",
                    "-DSTATIC_LINK=ON",
                    "-DUSE_SDLMIXER=OFF",
                    "-DUSE_OPENAL=OFF",
                    "-DUSE_LIBVLC=OFF",
                    "-DUSE_FREETYPE=OFF",
                    "-DUSE_PNG=OFF",
                    "-DUSE_VORBIS=OFF",
                    "-DOPENGL_BACKEND=None",
                    "-DSKIP_DEMO_DATA=ON",
                    "-DUSE_TESTS=OFF",
                    "-DGEMRB_ANDROID_BOOTSTRAP_ONLY=ON"
                )
                targets += listOf("gemrb")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = repoRoot.resolve("CMakeLists.txt")
            version = "3.31.6"
        }
    }

    sourceSets {
        getByName("main") {
            java.srcDir(sdl2Root.resolve("android-project/app/src/main/java"))
            jniLibs.srcDir(depsDir.resolve("jniLibs"))
        }
    }

    buildTypes {
        getByName("debug") {
            isMinifyEnabled = false
        }
        getByName("release") {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

val prepareAndroidDependencies by tasks.registering(Exec::class) {
    workingDir = rootProject.projectDir
    commandLine("bash", "scripts/prepare-dependencies.sh")
}

tasks.named("preBuild") {
    dependsOn(prepareAndroidDependencies)
}
