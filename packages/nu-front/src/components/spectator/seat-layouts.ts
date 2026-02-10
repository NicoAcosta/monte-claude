export interface SeatPosition {
  top: number
  left: number
}

export const SEAT_LAYOUTS: Record<number, SeatPosition[]> = {
  2: [
    { top: 85, left: 50 },
    { top: 5, left: 50 },
  ],
  3: [
    { top: 85, left: 50 },
    { top: 20, left: 10 },
    { top: 20, left: 90 },
  ],
  4: [
    { top: 85, left: 50 },
    { top: 50, left: 3 },
    { top: 5, left: 50 },
    { top: 50, left: 97 },
  ],
  5: [
    { top: 85, left: 50 },
    { top: 65, left: 3 },
    { top: 10, left: 18 },
    { top: 10, left: 82 },
    { top: 65, left: 97 },
  ],
  6: [
    { top: 85, left: 50 },
    { top: 60, left: 2 },
    { top: 10, left: 15 },
    { top: 5, left: 50 },
    { top: 10, left: 85 },
    { top: 60, left: 98 },
  ],
  7: [
    { top: 85, left: 50 },
    { top: 70, left: 2 },
    { top: 25, left: 3 },
    { top: 5, left: 30 },
    { top: 5, left: 70 },
    { top: 25, left: 97 },
    { top: 70, left: 98 },
  ],
  8: [
    { top: 85, left: 50 },
    { top: 70, left: 2 },
    { top: 30, left: 2 },
    { top: 5, left: 25 },
    { top: 5, left: 50 },
    { top: 5, left: 75 },
    { top: 30, left: 98 },
    { top: 70, left: 98 },
  ],
}
