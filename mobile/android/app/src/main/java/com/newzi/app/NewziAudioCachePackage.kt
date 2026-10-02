package com.newzi.app

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.bridge.ReactMethod
import com.facebook.react.uimanager.ViewManager
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.Executors

class NewziAudioCachePackage : ReactPackage {
  override fun createNativeModules(context: ReactApplicationContext): List<NativeModule> =
    listOf(NewziAudioCacheModule(context))

  override fun createViewManagers(context: ReactApplicationContext): List<ViewManager<*, *>> = emptyList()
}

class NewziAudioCacheModule(private val context: ReactApplicationContext) : ReactContextBaseJavaModule(context) {
  private val executor = Executors.newSingleThreadExecutor()
  override fun getName(): String = "NewziAudioCache"
  private fun key(url: String): String = MessageDigest.getInstance("SHA-256")
    .digest(url.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

  @ReactMethod
  fun download(url: String, token: String, promise: Promise) {
    executor.execute {
      var temporary: File? = null
      var connection: HttpURLConnection? = null
      try {
        val parsed = URL(url)
        require(parsed.protocol == "http" || parsed.protocol == "https") { "invalid audio URL" }
        require(token.isNotBlank()) { "authentication required" }
        val key = key(url)
        val directory = File(context.cacheDir, "newzi-audio")
        directory.mkdirs()
        val cached = listOf("wav", "mp3", "m4a", "aac").map { File(directory, "$key.$it") }
          .firstOrNull { it.isFile && it.length() > 0 }
        if (cached != null) {
          promise.resolve(cached.absolutePath)
          return@execute
        }
        connection = parsed.openConnection() as HttpURLConnection
        connection.setRequestProperty("Authorization", "Bearer $token")
        connection.connectTimeout = 10000
        connection.readTimeout = 120000
        connection.instanceFollowRedirects = false
        if (connection.responseCode != 200) throw IllegalStateException("audio HTTP ${connection.responseCode}")
        val extension = when (connection.contentType?.substringBefore(';')?.trim()?.lowercase()) {
          "audio/mpeg", "audio/mp3" -> "mp3"
          "audio/mp4", "audio/x-m4a" -> "m4a"
          "audio/aac" -> "aac"
          else -> "wav"
        }
        val target = File(directory, "$key.$extension")
        val temp = File(directory, "$key.tmp")
        temporary = temp
        connection.inputStream.use { input -> temp.outputStream().use { output -> input.copyTo(output) } }
        require(temp.length() > 0) { "empty audio file" }
        if (!temp.renameTo(target)) throw IllegalStateException("audio cache write failed")
        promise.resolve(target.absolutePath)
      } catch (error: Exception) {
        temporary?.delete()
        promise.reject("AUDIO_DOWNLOAD_FAILED", error.message, error)
      } finally {
        connection?.disconnect()
      }
    }
  }

  @ReactMethod
  fun savePosition(url: String, seconds: Double) {
    context.getSharedPreferences("newzi-audio", 0).edit().putFloat(key(url), seconds.toFloat()).apply()
  }

  @ReactMethod
  fun getPosition(url: String, promise: Promise) {
    promise.resolve(context.getSharedPreferences("newzi-audio", 0).getFloat(key(url), 0f).toDouble())
  }

  @ReactMethod
  fun clear() {
    File(context.cacheDir, "newzi-audio").deleteRecursively()
    context.getSharedPreferences("newzi-audio", 0).edit().clear().apply()
  }
}
