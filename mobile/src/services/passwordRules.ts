/** Password rules shared by sign-up and the in-app password change. */
export function passwordChecks(password: string) {
  return {
    longEnough: password.length >= 8,
    letterAndNumber: /[A-Za-zÀ-ÿ]/.test(password) && /\d/.test(password),
    special: /[^A-Za-zÀ-ÿ0-9]/.test(password),
  };
}

export const isStrongEnough = (password: string) => { const checks = passwordChecks(password); return checks.longEnough && checks.letterAndNumber; };
