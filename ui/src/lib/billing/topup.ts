// Self-serve credit top-up seam. The real implementation (create a Razorpay
// order on the backend + open Razorpay checkout) lands on this branch as a
// separate concurrent task. Until then the seam throws so the UI can surface a
// friendly "not wired yet" message without any placeholder charge flow.

/** Starts a self-serve top-up for `amountAed`. Implemented by the Razorpay integration. */
export async function startTopUp(amountAed: number): Promise<void> {
  // TODO(razorpay): create order on backend + open Razorpay checkout.
  // Reference the amount so the signature is honoured before the impl lands.
  void amountAed;
  throw new Error("Top-up not wired yet");
}

// Minimum self-serve top-up amount in AED.
export const MIN_TOPUP_AED = 20;

// Maximum self-serve top-up amount in AED (guards against fat-finger typos
// before the real Razorpay order is created).
export const MAX_TOPUP_AED = 40000;

// Preset chip amounts (AED).
export const TOPUP_PRESETS = [20, 50, 100, 200, 500] as const;
