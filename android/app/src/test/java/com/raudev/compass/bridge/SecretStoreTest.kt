package com.raudev.compass.bridge

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import javax.crypto.KeyGenerator

class SecretStoreTest {
    private fun testKey() = KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    @Test
    fun roundTripsTokenWithFreshIvEachTime() {
        val key = testKey()
        val first = TokenCipher.encrypt("secret-token-123", key)
        val second = TokenCipher.encrypt("secret-token-123", key)

        assertTrue(TokenCipher.isEncrypted(first))
        assertNotEquals(first, second)
        assertEquals("secret-token-123", TokenCipher.decrypt(first, key))
        assertEquals("secret-token-123", TokenCipher.decrypt(second, key))
    }

    @Test
    fun rejectsWrongKeyPlaintextAndCorruptValues() {
        val key = testKey()
        val other = testKey()
        val encrypted = TokenCipher.encrypt("secret-token-123", key)

        assertFalse(TokenCipher.isEncrypted("plaintext-token"))
        assertNull(TokenCipher.decrypt("plaintext-token", key))
        assertNull(TokenCipher.decrypt(encrypted, other))
        assertNull(TokenCipher.decrypt("v1:not-base64:broken", key))
    }
}
