package com.raudev.compass.bridge

import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.MealType
import androidx.health.connect.client.records.NutritionRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import androidx.health.connect.client.records.metadata.Device
import androidx.health.connect.client.records.metadata.Metadata
import androidx.health.connect.client.units.Energy
import androidx.health.connect.client.units.Length
import androidx.health.connect.client.units.Mass
import androidx.health.connect.client.units.Percentage
import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File
import java.time.Instant
import java.time.ZoneOffset

class HealthTypesTest {
    private val start = Instant.parse("2026-10-17T21:00:00Z")
    private val end = Instant.parse("2026-10-18T05:00:00Z")
    private val offset = ZoneOffset.ofHours(2)
    private fun meta(id: String) = Metadata.autoRecordedWithId(id, Device(type = Device.TYPE_WATCH))

    private val records = listOf(
        SleepSessionRecord(
            startTime = start, startZoneOffset = offset, endTime = end, endZoneOffset = offset,
            metadata = meta("sleep-1"),
            stages = listOf(
                SleepSessionRecord.Stage(start, start.plusSeconds(3600), SleepSessionRecord.STAGE_TYPE_LIGHT),
                SleepSessionRecord.Stage(start.plusSeconds(3600), end, SleepSessionRecord.STAGE_TYPE_DEEP),
            ),
        ),
        StepsRecord(start, offset, start.plusSeconds(600), offset, 1234, meta("steps-1")),
        HeartRateRecord(
            start, offset, start.plusSeconds(120), offset,
            listOf(HeartRateRecord.Sample(start, 58), HeartRateRecord.Sample(start.plusSeconds(60), 61)),
            meta("hr-1"),
        ),
        RestingHeartRateRecord(start, offset, 52, meta("rhr-1")),
        ExerciseSessionRecord(
            startTime = start, startZoneOffset = offset, endTime = start.plusSeconds(4500), endZoneOffset = offset,
            metadata = meta("ex-1"),
            exerciseType = ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING, title = "Leg day",
        ),
        NutritionRecord(
            startTime = start, startZoneOffset = offset, endTime = start.plusSeconds(900), endZoneOffset = offset,
            metadata = meta("meal-1"),
            energy = Energy.kilocalories(650.0), protein = Mass.grams(40.0), mealType = MealType.MEAL_TYPE_BREAKFAST,
        ),
        WeightRecord(start, offset, Mass.kilograms(78.7), meta("weight-1")),
        TotalCaloriesBurnedRecord(start, offset, end, offset, Energy.kilocalories(2400.0), meta("kcal-1")),
        OxygenSaturationRecord(start, offset, Percentage(97.0), meta("spo2-1")),
        HeartRateVariabilityRmssdRecord(start, offset, 48.5, meta("hrv-1")),
        RespiratoryRateRecord(start, offset, 14.2, meta("rr-1")),
        DistanceRecord(start, offset, start.plusSeconds(600), offset, Length.meters(820.0), meta("dist-1")),
        ActiveCaloriesBurnedRecord(start, offset, start.plusSeconds(600), offset, Energy.kilocalories(55.0), meta("act-1")),
    )

    @Test
    fun everyTypeMapsToTheWireFormat() {
        val json = records.map { HealthTypes.toJson(it)!! }
        assertEquals(HealthTypes.ALL.map { it.name }, json.map { it.getString("type") })

        val sleep = json[0]
        assertEquals("sleep-1", sleep.getString("id"))
        assertEquals("2026-10-17T21:00:00Z", sleep.getString("start"))
        assertEquals("2026-10-18T05:00:00Z", sleep.getString("end"))
        val stages = sleep.getJSONObject("data").getJSONArray("stages")
        assertEquals("light", stages.getJSONObject(0).getString("stage"))
        assertEquals("deep", stages.getJSONObject(1).getString("stage"))

        assertEquals(1234, json[1].getJSONObject("data").getInt("count"))
        assertEquals(61, json[2].getJSONObject("data").getJSONArray("samples").getJSONObject(1).getInt("bpm"))
        assertEquals(false, json[3].has("end"))
        assertEquals("strength_training", json[4].getJSONObject("data").getString("exercise"))
        assertEquals("Leg day", json[4].getJSONObject("data").getString("title"))
        assertEquals("breakfast", json[5].getJSONObject("data").getString("meal_type"))
        assertEquals(40.0, json[5].getJSONObject("data").getDouble("protein_g"), 0.001)
        assertEquals(78.7, json[6].getJSONObject("data").getDouble("kg"), 0.001)
        assertEquals(97.0, json[8].getJSONObject("data").getDouble("percent"), 0.001)
        assertEquals(48.5, json[9].getJSONObject("data").getDouble("rmssd_ms"), 0.001)
        assertEquals(14.2, json[10].getJSONObject("data").getDouble("rate"), 0.001)
        assertEquals(820.0, json[11].getJSONObject("data").getDouble("meters"), 0.001)
        assertEquals(55.0, json[12].getJSONObject("data").getDouble("kcal"), 0.001)

        // Contract check against the backend: backend/tests can validate this file with the API schema.
        File("build/contract").mkdirs()
        File("build/contract/records.json").writeText(JSONArray(json).toString(2))
    }
}
