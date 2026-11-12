package com.raudev.compass.bridge

import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.MealType
import androidx.health.connect.client.records.NutritionRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.records.WeightRecord
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import kotlin.reflect.KClass

/** A Health Connect record type the bridge reads, with its name on the wire (the `type` field
 * that /api/ingest/health expects). Keep in sync with the manifest permissions. */
data class HealthType(val name: String, val recordClass: KClass<out Record>) {
    val permission: String get() = HealthPermission.getReadPermission(recordClass)
}

object HealthTypes {
    val ALL = listOf(
        HealthType("sleep", SleepSessionRecord::class),
        HealthType("steps", StepsRecord::class),
        HealthType("heart_rate", HeartRateRecord::class),
        HealthType("resting_heart_rate", RestingHeartRateRecord::class),
        HealthType("exercise", ExerciseSessionRecord::class),
        HealthType("nutrition", NutritionRecord::class),
        HealthType("weight", WeightRecord::class),
        HealthType("total_calories", TotalCaloriesBurnedRecord::class),
        // Written by some watches only (Zepp depends on the model); nothing arrives otherwise.
        HealthType("oxygen_saturation", OxygenSaturationRecord::class),
        HealthType("heart_rate_variability", HeartRateVariabilityRmssdRecord::class),
        HealthType("respiratory_rate", RespiratoryRateRecord::class),
        HealthType("distance", DistanceRecord::class),
        HealthType("active_calories", ActiveCaloriesBurnedRecord::class),
    )

    val BACKGROUND = HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
    val HISTORY = HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY

    /** Everything the app asks for in one go. */
    val PERMISSIONS: Set<String> = ALL.map { it.permission }.toSet() + BACKGROUND + HISTORY

    /** The record as JSON for the API, or null for types the bridge does not send. */
    fun toJson(record: Record): JSONObject? {
        val (type, start, end, data) = when (record) {
            is SleepSessionRecord -> Mapped("sleep", record.startTime, record.endTime, sleep(record))
            is StepsRecord -> Mapped(
                "steps", record.startTime, record.endTime, JSONObject().put("count", record.count),
            )
            is HeartRateRecord -> Mapped("heart_rate", record.startTime, record.endTime, heartRate(record))
            is RestingHeartRateRecord -> Mapped(
                "resting_heart_rate", record.time, null, JSONObject().put("bpm", record.beatsPerMinute),
            )
            is ExerciseSessionRecord -> Mapped("exercise", record.startTime, record.endTime, exercise(record))
            is NutritionRecord -> Mapped("nutrition", record.startTime, record.endTime, nutrition(record))
            is WeightRecord -> Mapped(
                "weight", record.time, null, JSONObject().put("kg", record.weight.inKilograms),
            )
            is TotalCaloriesBurnedRecord -> Mapped(
                "total_calories", record.startTime, record.endTime,
                JSONObject().put("kcal", record.energy.inKilocalories),
            )
            is OxygenSaturationRecord -> Mapped(
                "oxygen_saturation", record.time, null, JSONObject().put("percent", record.percentage.value),
            )
            is HeartRateVariabilityRmssdRecord -> Mapped(
                "heart_rate_variability", record.time, null,
                JSONObject().put("rmssd_ms", record.heartRateVariabilityMillis),
            )
            is RespiratoryRateRecord -> Mapped(
                "respiratory_rate", record.time, null, JSONObject().put("rate", record.rate),
            )
            is DistanceRecord -> Mapped(
                "distance", record.startTime, record.endTime, JSONObject().put("meters", record.distance.inMeters),
            )
            is ActiveCaloriesBurnedRecord -> Mapped(
                "active_calories", record.startTime, record.endTime,
                JSONObject().put("kcal", record.energy.inKilocalories),
            )
            else -> return null
        }
        val meta = record.metadata
        return JSONObject()
            .put("id", meta.id)
            .put("type", type)
            .put("source", meta.dataOrigin.packageName)
            .put("start", start.toString())
            .apply { if (end != null) put("end", end.toString()) }
            .put("last_modified", meta.lastModifiedTime.toString())
            .put("data", data)
    }

    private data class Mapped(val type: String, val start: Instant, val end: Instant?, val data: JSONObject)

    private fun sleep(record: SleepSessionRecord): JSONObject {
        val stages = JSONArray()
        for (stage in record.stages) {
            stages.put(
                JSONObject()
                    .put("start", stage.startTime.toString())
                    .put("end", stage.endTime.toString())
                    .put("stage", sleepStage(stage.stage)),
            )
        }
        return JSONObject().put("stages", stages).putOpt("title", record.title)
    }

    private fun sleepStage(stage: Int): String = when (stage) {
        SleepSessionRecord.STAGE_TYPE_AWAKE -> "awake"
        SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED -> "awake_in_bed"
        SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> "out_of_bed"
        SleepSessionRecord.STAGE_TYPE_SLEEPING -> "sleeping"
        SleepSessionRecord.STAGE_TYPE_LIGHT -> "light"
        SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
        SleepSessionRecord.STAGE_TYPE_REM -> "rem"
        else -> "unknown"
    }

    private fun heartRate(record: HeartRateRecord): JSONObject {
        val samples = JSONArray()
        for (sample in record.samples) {
            samples.put(JSONObject().put("time", sample.time.toString()).put("bpm", sample.beatsPerMinute))
        }
        return JSONObject().put("samples", samples)
    }

    private fun exercise(record: ExerciseSessionRecord): JSONObject = JSONObject()
        .put("exercise_type", record.exerciseType)
        .put("exercise", exerciseName(record.exerciseType))
        .putOpt("title", record.title)

    private fun exerciseName(type: Int): String = when (type) {
        ExerciseSessionRecord.EXERCISE_TYPE_STRENGTH_TRAINING -> "strength_training"
        ExerciseSessionRecord.EXERCISE_TYPE_WEIGHTLIFTING -> "weightlifting"
        ExerciseSessionRecord.EXERCISE_TYPE_CALISTHENICS -> "calisthenics"
        ExerciseSessionRecord.EXERCISE_TYPE_HIGH_INTENSITY_INTERVAL_TRAINING -> "hiit"
        ExerciseSessionRecord.EXERCISE_TYPE_RUNNING -> "running"
        ExerciseSessionRecord.EXERCISE_TYPE_RUNNING_TREADMILL -> "running_treadmill"
        ExerciseSessionRecord.EXERCISE_TYPE_WALKING -> "walking"
        ExerciseSessionRecord.EXERCISE_TYPE_HIKING -> "hiking"
        ExerciseSessionRecord.EXERCISE_TYPE_BIKING -> "biking"
        ExerciseSessionRecord.EXERCISE_TYPE_BIKING_STATIONARY -> "biking_stationary"
        ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_POOL -> "swimming_pool"
        ExerciseSessionRecord.EXERCISE_TYPE_SWIMMING_OPEN_WATER -> "swimming_open_water"
        ExerciseSessionRecord.EXERCISE_TYPE_ELLIPTICAL -> "elliptical"
        ExerciseSessionRecord.EXERCISE_TYPE_ROWING_MACHINE -> "rowing_machine"
        ExerciseSessionRecord.EXERCISE_TYPE_STAIR_CLIMBING_MACHINE -> "stair_climbing_machine"
        ExerciseSessionRecord.EXERCISE_TYPE_STRETCHING -> "stretching"
        ExerciseSessionRecord.EXERCISE_TYPE_YOGA -> "yoga"
        ExerciseSessionRecord.EXERCISE_TYPE_PILATES -> "pilates"
        ExerciseSessionRecord.EXERCISE_TYPE_SOCCER -> "soccer"
        ExerciseSessionRecord.EXERCISE_TYPE_ROCK_CLIMBING -> "rock_climbing"
        ExerciseSessionRecord.EXERCISE_TYPE_BASKETBALL -> "basketball"
        ExerciseSessionRecord.EXERCISE_TYPE_VOLLEYBALL -> "volleyball"
        ExerciseSessionRecord.EXERCISE_TYPE_BADMINTON -> "badminton"
        ExerciseSessionRecord.EXERCISE_TYPE_TENNIS -> "tennis"
        ExerciseSessionRecord.EXERCISE_TYPE_TABLE_TENNIS -> "table_tennis"
        ExerciseSessionRecord.EXERCISE_TYPE_BOXING -> "boxing"
        ExerciseSessionRecord.EXERCISE_TYPE_MARTIAL_ARTS -> "martial_arts"
        ExerciseSessionRecord.EXERCISE_TYPE_DANCING -> "dancing"
        ExerciseSessionRecord.EXERCISE_TYPE_OTHER_WORKOUT -> "other"
        else -> "type_$type"
    }

    private fun nutrition(record: NutritionRecord): JSONObject = JSONObject()
        .put("meal_type", mealType(record.mealType))
        .putOpt("name", record.name)
        .putOpt("energy_kcal", record.energy?.inKilocalories)
        .putOpt("protein_g", record.protein?.inGrams)
        .putOpt("carbs_g", record.totalCarbohydrate?.inGrams)
        .putOpt("fat_g", record.totalFat?.inGrams)
        .putOpt("saturated_fat_g", record.saturatedFat?.inGrams)
        .putOpt("fiber_g", record.dietaryFiber?.inGrams)
        .putOpt("sugar_g", record.sugar?.inGrams)
        .putOpt("sodium_mg", record.sodium?.inMilligrams)
        .putOpt("potassium_mg", record.potassium?.inMilligrams)
        .putOpt("calcium_mg", record.calcium?.inMilligrams)
        .putOpt("iron_mg", record.iron?.inMilligrams)

    private fun mealType(type: Int): String = when (type) {
        MealType.MEAL_TYPE_BREAKFAST -> "breakfast"
        MealType.MEAL_TYPE_LUNCH -> "lunch"
        MealType.MEAL_TYPE_DINNER -> "dinner"
        MealType.MEAL_TYPE_SNACK -> "snack"
        else -> "unknown"
    }
}
