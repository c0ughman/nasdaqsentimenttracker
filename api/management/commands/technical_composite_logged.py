def calculate_technical_composite_score(indicators):
    """
    Convert technical indicators into a single sentiment-like score (-100 to +100).
    This creates a unified "Technical Sentiment" that can be combined with news/social sentiment.

    Components:
    - RSI (30%): Oversold (<30) = bullish, Overbought (>70) = bearish
    - MACD (25%): Positive histogram = bullish, negative = bearish
    - Bollinger Bands (20%): Price position relative to bands
    - Moving Average Crossover (15%): Short-term vs long-term trend
    - Stochastic (10%): Momentum indicator

    Args:
        indicators: Dictionary with calculated technical indicators

    Returns:
        Float: Technical composite score from -100 (very bearish) to +100 (very bullish)
    """
    print("\n" + "="*80)
    print("📊 CALCULATING TECHNICAL COMPOSITE SCORE")
    print("="*80)

    if not indicators:
        print("⚠️  ERROR: No indicators provided - returning 0.0")
        return 0.0

    print(f"✓ Received {len(indicators)} indicators:")
    for key, value in indicators.items():
        value_str = f"{value}" if value is not None else "None"
        type_str = type(value).__name__ if value is not None else "NoneType"
        print(f"  • {key:20s} = {value_str:>12s} (type: {type_str})")

    scores = []
    weights = []

    # 1. RSI Score (30% weight) - Mean reversion indicator
    print("\n1️⃣  RSI SCORE (30% weight):")
    rsi = indicators.get('rsi_14')
    if rsi is not None:
        try:
            rsi_val = float(rsi)
            if rsi_val < 30:
                rsi_score = 100 * (30 - rsi_val) / 30
                print(f"   RSI = {rsi_val:.2f} (OVERSOLD - Bullish)")
            elif rsi_val > 70:
                rsi_score = -100 * (rsi_val - 70) / 30
                print(f"   RSI = {rsi_val:.2f} (OVERBOUGHT - Bearish)")
            else:
                rsi_score = ((rsi_val - 50) / 20) * 20
                print(f"   RSI = {rsi_val:.2f} (NEUTRAL)")

            scores.append(rsi_score)
            weights.append(0.30)
            print(f"   ✓ RSI Score: {rsi_score:+.2f} (weight: 30%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating RSI score: {e}")
    else:
        print("   ⊘ RSI is None - skipping")

    # 2. MACD Score (25% weight) - Trend momentum
    print("\n2️⃣  MACD SCORE (25% weight):")
    macd_histogram = indicators.get('macd_histogram')
    if macd_histogram is not None:
        try:
            macd_val = float(macd_histogram)
            macd_score = max(min(macd_val * 20, 100), -100)
            scores.append(macd_score)
            weights.append(0.25)
            direction = "Bullish" if macd_val > 0 else "Bearish" if macd_val < 0 else "Neutral"
            print(f"   MACD Histogram = {macd_val:.4f} ({direction})")
            print(f"   ✓ MACD Score: {macd_score:+.2f} (weight: 25%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating MACD score: {e}")
    else:
        print("   ⊘ MACD Histogram is None - skipping")

    # 3. Bollinger Bands Score (20% weight) - Volatility & position
    print("\n3️⃣  BOLLINGER BANDS SCORE (20% weight):")
    bb_upper = indicators.get('bb_upper')
    bb_middle = indicators.get('bb_middle')
    bb_lower = indicators.get('bb_lower')
    current_price = indicators.get('qqq_price')

    if all(x is not None for x in [bb_upper, bb_middle, bb_lower, current_price]):
        try:
            # Convert to float to avoid Decimal type issues
            bb_upper_f = float(bb_upper)
            bb_lower_f = float(bb_lower)
            current_price_f = float(current_price)

            print(f"   BB Upper:  {bb_upper_f:.2f}")
            print(f"   BB Middle: {float(bb_middle):.2f}")
            print(f"   BB Lower:  {bb_lower_f:.2f}")
            print(f"   Price:     {current_price_f:.2f}")

            bb_range = bb_upper_f - bb_lower_f
            if bb_range > 0:
                position = (current_price_f - bb_lower_f) / bb_range
                bb_score = (0.5 - position) * 200

                if position < 0.3:
                    pos_desc = "Near Lower Band (Oversold - Bullish)"
                elif position > 0.7:
                    pos_desc = "Near Upper Band (Overbought - Bearish)"
                else:
                    pos_desc = "Middle of Bands (Neutral)"

                print(f"   Position in bands: {position:.2%} - {pos_desc}")
                scores.append(bb_score)
                weights.append(0.20)
                print(f"   ✓ BB Score: {bb_score:+.2f} (weight: 20%)")
            else:
                print(f"   ✗ ERROR: BB range is {bb_range} (should be > 0)")
        except Exception as e:
            print(f"   ✗ ERROR calculating BB score: {e}")
            import traceback
            traceback.print_exc()
    else:
        missing = [k for k, v in {'bb_upper': bb_upper, 'bb_middle': bb_middle, 'bb_lower': bb_lower, 'qqq_price': current_price}.items() if v is None]
        print(f"   ⊘ Missing values: {', '.join(missing)} - skipping")

    # 4. Moving Average Crossover Score (15% weight) - Trend direction
    print("\n4️⃣  MOVING AVERAGE CROSSOVER SCORE (15% weight):")
    ema_9 = indicators.get('ema_9')
    ema_20 = indicators.get('ema_20')

    if ema_9 is not None and ema_20 is not None:
        try:
            # Convert to float to avoid Decimal type issues
            ema_9_f = float(ema_9)
            ema_20_f = float(ema_20)

            print(f"   EMA 9:  {ema_9_f:.2f}")
            print(f"   EMA 20: {ema_20_f:.2f}")

            crossover_diff = ((ema_9_f - ema_20_f) / ema_20_f) * 100 if ema_20_f != 0 else 0
            ma_score = max(min(crossover_diff * 50, 100), -100)

            if ema_9_f > ema_20_f:
                print(f"   Short-term above long-term ({crossover_diff:+.2f}%) - Bullish")
            else:
                print(f"   Short-term below long-term ({crossover_diff:+.2f}%) - Bearish")

            scores.append(ma_score)
            weights.append(0.15)
            print(f"   ✓ MA Crossover Score: {ma_score:+.2f} (weight: 15%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating MA score: {e}")
            import traceback
            traceback.print_exc()
    else:
        missing = [k for k, v in {'ema_9': ema_9, 'ema_20': ema_20}.items() if v is None]
        print(f"   ⊘ Missing values: {', '.join(missing)} - skipping")

    # 5. Stochastic Score (10% weight) - Momentum
    print("\n5️⃣  STOCHASTIC SCORE (10% weight):")
    stoch_k = indicators.get('stoch_k')
    stoch_d = indicators.get('stoch_d')

    if stoch_k is not None and stoch_d is not None:
        try:
            stoch_k_f = float(stoch_k)
            stoch_d_f = float(stoch_d)
            stoch_avg = (stoch_k_f + stoch_d_f) / 2

            print(f"   Stoch %K: {stoch_k_f:.2f}")
            print(f"   Stoch %D: {stoch_d_f:.2f}")
            print(f"   Average:  {stoch_avg:.2f}")

            if stoch_avg < 20:
                stoch_score = 100 * (20 - stoch_avg) / 20
                print(f"   Below 20 (Oversold - Bullish)")
            elif stoch_avg > 80:
                stoch_score = -100 * (stoch_avg - 80) / 20
                print(f"   Above 80 (Overbought - Bearish)")
            else:
                stoch_score = ((50 - stoch_avg) / 30) * 20
                print(f"   Middle range (Neutral)")

            scores.append(stoch_score)
            weights.append(0.10)
            print(f"   ✓ Stochastic Score: {stoch_score:+.2f} (weight: 10%)")
        except Exception as e:
            print(f"   ✗ ERROR calculating Stochastic score: {e}")
    else:
        print("   ⊘ Stochastic values are None - skipping")

    # Calculate weighted average
    print("\n" + "="*80)
    print("📊 FINAL CALCULATION")
    print("="*80)

    if not scores:
        print("⚠️  ERROR: No scores calculated - returning 0.0")
        print("   This means ALL indicators were None or had errors!")
        return 0.0

    # Normalize weights to sum to 1.0
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    print(f"✓ Calculated {len(scores)} component scores")
    print(f"  Total weight before normalization: {total_weight:.2f}")
    print(f"\n  Component Breakdown:")
    for i, (score, weight, norm_weight) in enumerate(zip(scores, weights, normalized_weights), 1):
        contribution = score * norm_weight
        print(f"    {i}. Score: {score:+7.2f} × Weight: {norm_weight:5.1%} = {contribution:+7.2f}")

    composite_score = sum(score * weight for score, weight in zip(scores, normalized_weights))

    print(f"\n🎯 TECHNICAL COMPOSITE SCORE: {composite_score:+.2f}")
    print("="*80 + "\n")

    return round(composite_score, 2)
