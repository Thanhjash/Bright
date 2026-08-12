/**
 * Single re-export point for the Bright wire contracts.
 *
 * Everything in this package imports Emotion / ActPayload / EMOTION_MOTION_GROUP /
 * TAG_* from here, and this file is the ONLY place that knows where the contracts
 * package physically lives. Nothing in airi-bridge may redefine those types.
 *
 * See packages/contracts/PROTOCOL.md — it is authoritative.
 */
export * from '../../contracts/src/index'
