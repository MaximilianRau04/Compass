package com.raudev.compass.bridge

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Encrypts the ingest bearer token with a hardware-backed AES-256-GCM key in AndroidKeyStore.
 * No user-auth gate on the key so WorkManager can sync in the background (matching iOS Keychain's
 * AfterFirstUnlock). Stored values carry a "v1:" prefix so existing plaintext tokens migrate
 * transparently on first read.
 */
internal object TokenCipher {
    const val PREFIX = "v1:"
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val TAG_BITS = 128

    fun isEncrypted(stored: String): Boolean = stored.startsWith(PREFIX)

    fun encrypt(plaintext: String, key: SecretKey): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        val iv = Base64.getEncoder().encodeToString(cipher.iv)
        val body = Base64.getEncoder().encodeToString(ciphertext)
        return "$PREFIX$iv:$body"
    }

    fun decrypt(stored: String, key: SecretKey): String? {
        if (!isEncrypted(stored)) return null
        val parts = stored.removePrefix(PREFIX).split(":", limit = 2)
        if (parts.size != 2) return null
        return runCatching {
            val iv = Base64.getDecoder().decode(parts[0])
            val body = Base64.getDecoder().decode(parts[1])
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(TAG_BITS, iv))
            String(cipher.doFinal(body), Charsets.UTF_8)
        }.getOrNull()
    }
}

internal object SecretStore {
    private const val PROVIDER = "AndroidKeyStore"
    private const val ALIAS = "compass_bridge_token"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance(PROVIDER).apply { load(null) }
        (store.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        val spec = KeyGenParameterSpec.Builder(
            ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()
        generator.init(spec)
        return generator.generateKey()
    }

    fun encrypt(plaintext: String): String = TokenCipher.encrypt(plaintext, key())

    fun decrypt(stored: String): String? = TokenCipher.decrypt(stored, key())
}
