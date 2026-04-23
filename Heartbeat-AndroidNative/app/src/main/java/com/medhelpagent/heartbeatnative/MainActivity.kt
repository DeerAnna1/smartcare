package com.medhelpagent.heartbeatnative

import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.RadioButton
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.medhelpagent.heartbeatnative.databinding.ActivityMainBinding
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.math.max
import kotlin.math.min

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val client = OkHttpClient()
    private val ui = Handler(Looper.getMainLooper())
    private val loopRunnable = object : Runnable {
        override fun run() {
            sendOnce()
            val sec = parseIntervalSec()
            ui.postDelayed(this, sec * 1000L)
        }
    }

    private var heartRate: Int = 70
    private var looping = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        restoreSettings()
        setupButtons()
        renderHeartRate()
    }

    override fun onStop() {
        super.onStop()
        persistSettings()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopLoop()
    }

    private fun setupButtons() {
        bindStepButton(binding.btnMinus1) { heartRate = max(40, heartRate - 1) }
        bindStepButton(binding.btnPlus1) { heartRate = min(180, heartRate + 1) }
        bindStepButton(binding.btnMinus5) { heartRate = max(40, heartRate - 5) }
        bindStepButton(binding.btnPlus5) { heartRate = min(180, heartRate + 5) }

        binding.btnPreset70.setOnClickListener { setPreset(70) }
        binding.btnPreset105.setOnClickListener { setPreset(105) }
        binding.btnPreset128.setOnClickListener { setPreset(128) }

        binding.btnSendOnce.setOnClickListener { sendOnce() }
        binding.btnToggleLoop.setOnClickListener {
            if (looping) stopLoop() else startLoop()
        }
    }

    private fun bindStepButton(button: Button, action: () -> Unit) {
        button.setOnClickListener {
            action.invoke()
            renderHeartRate()
        }
    }

    private fun setPreset(value: Int) {
        heartRate = value
        renderHeartRate()
    }

    private fun renderHeartRate() {
        binding.tvHeartRate.text = "$heartRate bpm"
        binding.tvRisk.text = "预测风险：${riskText(heartRate)}"
    }

    private fun riskText(v: Int): String {
        return when {
            v >= 120 -> "高风险"
            v >= 100 -> "中风险"
            else -> "正常"
        }
    }

    private fun parseIntervalSec(): Int {
        val raw = binding.etIntervalSec.text.toString().trim()
        return max(1, raw.toIntOrNull() ?: 5)
    }

    private fun startLoop() {
        looping = true
        binding.btnToggleLoop.text = "停止连续推送"
        ui.post(loopRunnable)
    }

    private fun stopLoop() {
        looping = false
        binding.btnToggleLoop.text = "开始连续推送"
        ui.removeCallbacks(loopRunnable)
    }

    private fun sendOnce() {
        val base = binding.etBaseUrl.text.toString().trim().trimEnd('/')
        if (base.isEmpty()) {
            toast("请先填写 baseUrl")
            return
        }

        val mode = if (binding.rbSimulate.isChecked) "simulate" else "webhook"
        val token = binding.etToken.text.toString().trim()
        val userId = binding.etUserId.text.toString().trim()
        val secret = binding.etWebhookSecret.text.toString()

        if (mode == "simulate" && token.isEmpty()) {
            toast("simulate 模式需要 token")
            return
        }
        if (mode == "webhook" && userId.isEmpty()) {
            toast("webhook 模式需要 userId")
            return
        }
        if (mode == "webhook" && secret.isEmpty()) {
            toast("webhook 模式需要 webhookSecret")
            return
        }

        val eventId = "hb-${System.currentTimeMillis()}"
        val measuredAt = isoNow()
        val payload = JSONObject()
            .put("source", "heartbeat-native")
            .put("metric", "heart_rate")
            .put("value", heartRate)
            .put("unit", "bpm")
            .put("measured_at", measuredAt)
            .put("event_id", eventId)

        val requestBuilder = Request.Builder()
        val bodyJson = if (mode == "webhook") {
            payload.put("user_id", userId).toString()
        } else {
            payload.toString()
        }

        val url = if (mode == "simulate") "$base/api/v1/iot/simulate" else "$base/api/v1/iot/webhook"

        requestBuilder.url(url)
            .post(bodyJson.toRequestBody("application/json".toMediaType()))
            .addHeader("Content-Type", "application/json")

        if (mode == "simulate") {
            requestBuilder.addHeader("Authorization", "Bearer $token")
        } else {
            val ts = (System.currentTimeMillis() / 1000L).toString()
            val nonce = "native-${System.currentTimeMillis()}"
            val signature = signHmac(secret, ts, nonce, bodyJson)
            requestBuilder.addHeader("x-iot-timestamp", ts)
            requestBuilder.addHeader("x-iot-nonce", nonce)
            requestBuilder.addHeader("x-iot-signature", signature)
        }

        val reqLog = "req: ${payload.put("mode", mode)}"
        appendLog(reqLog)

        client.newCall(requestBuilder.build()).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    appendLog("err: ${e.message ?: "Network request failed"}")
                    toast("推送失败")
                }
            }

            override fun onResponse(call: Call, response: Response) {
                val text = response.body?.string().orEmpty()
                val parsed = runCatching { JSONObject(text) }.getOrNull()
                val pretty = parsed?.toString() ?: text.ifBlank { "(empty)" }
                runOnUiThread {
                    if (response.isSuccessful) {
                        appendLog("res: $pretty")
                    } else {
                        val detail = parsed?.opt("detail")?.toString()?.takeIf { it.isNotBlank() }
                            ?: "HTTP ${response.code}"
                        appendLog("err: $detail")
                        toast("推送失败")
                    }
                }
            }
        })
    }

    private fun signHmac(secret: String, timestamp: String, nonce: String, rawBody: String): String {
        val base = "$timestamp.$nonce.$rawBody"
        val mac = Mac.getInstance("HmacSHA256")
        val key = SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256")
        mac.init(key)
        val digest = mac.doFinal(base.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }


    private fun isoNow(): String {
        val fmt = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", java.util.Locale.US)
        fmt.timeZone = java.util.TimeZone.getTimeZone("UTC")
        return fmt.format(java.util.Date())
    }

    private fun timeNow(): String {
        val fmt = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
        return fmt.format(java.util.Date())
    }

    private fun appendLog(line: String) {
        val old = binding.tvLogs.text.toString()
        val ts = timeNow()
        val merged = if (old == "暂无日志") {
            "$ts\n$line"
        } else {
            "$ts\n$line\n\n$old"
        }
        binding.tvLogs.text = merged.take(8000)
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }

    private fun prefs() = getSharedPreferences("heartbeat_native", Context.MODE_PRIVATE)

    private fun persistSettings() {
        prefs().edit()
            .putString("base_url", binding.etBaseUrl.text.toString())
            .putString("token", binding.etToken.text.toString())
            .putString("user_id", binding.etUserId.text.toString())
            .putString("secret", binding.etWebhookSecret.text.toString())
            .putString("interval", binding.etIntervalSec.text.toString())
            .putInt("heart_rate", heartRate)
            .putString("mode", if (binding.rbSimulate.isChecked) "simulate" else "webhook")
            .apply()
    }

    private fun restoreSettings() {
        val p = prefs()
        binding.etBaseUrl.setText(p.getString("base_url", "http://127.0.0.1:8001") ?: "")
        binding.etToken.setText(p.getString("token", "") ?: "")
        binding.etUserId.setText(p.getString("user_id", "") ?: "")
        binding.etWebhookSecret.setText(p.getString("secret", "") ?: "")
        binding.etIntervalSec.setText(p.getString("interval", "5") ?: "5")
        heartRate = p.getInt("heart_rate", 70)
        val mode = p.getString("mode", "simulate") ?: "simulate"
        if (mode == "webhook") {
            binding.rbWebhook.isChecked = true
        } else {
            binding.rbSimulate.isChecked = true
        }
        binding.tvLogs.text = "暂无日志"
    }
}
