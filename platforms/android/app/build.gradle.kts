plugins {
    id("com.android.application")
}

val repoRoot = rootProject.projectDir.resolve("../..").canonicalFile
val depsDir = rootProject.projectDir.resolve(".deps").canonicalFile
val pythonPrefix = depsDir.resolve("python/prefix")
val iconvPrefix = depsDir.resolve("libiconv/prefix")
val freetypePrefix = depsDir.resolve("freetype/prefix")
val pngPrefix = depsDir.resolve("libpng/prefix")
val oggPrefix = depsDir.resolve("libogg/prefix")
val vorbisPrefix = depsDir.resolve("libvorbis/prefix")
val openalPrefix = depsDir.resolve("openal/prefix")
val sdl2Root = depsDir.resolve("sdl2")
val androidBootstrap = rootProject.projectDir.resolve("cmake/AndroidBootstrap.cmake")
val generatedAssetsDir = layout.buildDirectory.dir("generated/m1Assets").get().asFile

android {
    namespace = "org.gemrb.gemrb"
    compileSdk = 36
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "org.gemrb.gemrb"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "0.9.5-android-m4"

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
                    "-DGEMRB_ANDROID_FREETYPE_PREFIX=${freetypePrefix.absolutePath}",
                    "-DGEMRB_ANDROID_PNG_PREFIX=${pngPrefix.absolutePath}",
                    "-DGEMRB_ANDROID_OGG_INCLUDE_DIR=${oggPrefix.resolve("include").absolutePath}",
                    "-DVORBIS_FILE=${vorbisPrefix.resolve("include/vorbis").absolutePath}",
                    "-DVORBIS_LIBRARY=${vorbisPrefix.resolve("lib/libvorbisfile.a").absolutePath};${vorbisPrefix.resolve("lib/libvorbis.a").absolutePath};${oggPrefix.resolve("lib/libogg.a").absolutePath};m",
                    "-DGEMRB_ANDROID_OPENAL_PREFIX=${openalPrefix.absolutePath}",
                    "-DSDL_BACKEND=SDL2",
                    "-DSTATIC_LINK=ON",
                    "-DUSE_SDLMIXER=OFF",
                    "-DUSE_OPENAL=ON",
                    "-DUSE_LIBVLC=OFF",
                    "-DUSE_FREETYPE=ON",
                    "-DUSE_PNG=ON",
                    "-DUSE_VORBIS=ON",
                    "-DOPENGL_BACKEND=None",
                    "-DSKIP_DEMO_DATA=ON",
                    "-DUSE_TESTS=OFF"
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
            assets.srcDir(generatedAssetsDir)
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
    commandLine("bash", "-c", "bash scripts/prefetch-mirrors.sh && bash scripts/prepare-dependencies.sh && bash scripts/prepare-openal.sh")
}

val stageAndroidRuntimeAssets by tasks.registering(Sync::class) {
    dependsOn(prepareAndroidDependencies)
    into(generatedAssetsDir)

    from(repoRoot.resolve("gemrb/GUIScripts")) {
        into("runtime/gemrb/GUIScripts")
        exclude("**/__pycache__/**", "**/*.pyc")
    }
    from(repoRoot.resolve("gemrb/override")) {
        into("runtime/gemrb/override")
    }
    from(repoRoot.resolve("gemrb/unhardcoded")) {
        into("runtime/gemrb/unhardcoded")
    }
    from(repoRoot.resolve("demo")) {
        into("runtime/demo")
    }
    from(pythonPrefix.resolve("lib/python3.14")) {
        into("runtime/python/lib/python3.14")
        exclude(
            "**/__pycache__/**",
            "**/*.pyc",
            "**/test/**",
            "**/tests/**",
            "idlelib/**",
            "tkinter/**",
            "turtledemo/**",
            "ensurepip/**"
        )
    }

    doLast {
        val marker = generatedAssetsDir.resolve("runtime/VERSION")
        marker.parentFile.mkdirs()
        marker.writeText("m3-1\n")
    }
}

tasks.named("preBuild") {
    dependsOn(stageAndroidRuntimeAssets)
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(stageAndroidRuntimeAssets)
}
