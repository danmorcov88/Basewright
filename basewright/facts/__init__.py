"""Normalization of raw host facts into a typed, engine-agnostic model.

Raw facts arrive in whatever shape the collector produced them. Everything
downstream reads the normalized model instead, so a change in a collector cannot
ripple into the gate engine or the planner.
"""
