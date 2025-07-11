from decimal import Decimal, ROUND_HALF_UP

class Money:
    def __init__(self, amount: str | float | Decimal):
        if isinstance(amount, float):
            amount = str(amount)
        self.amount = Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @classmethod
    def from_cents(cls, cents: int) -> 'Money':
        return cls(Decimal(cents) / Decimal('100'))

    def to_cents(self) -> int:
        # multiply by 100 and round to nearest cent
        return int((self.amount * Decimal('100')).to_integral_value(rounding=ROUND_HALF_UP))

    def __add__(self, other: 'Money') -> 'Money':
        return Money(self.amount + other.amount)

    def __sub__(self, other: 'Money') -> 'Money':
        return Money(self.amount - other.amount)

    def __mul__(self, factor: int | Decimal | float) -> 'Money':
        return Money(self.amount * Decimal(str(factor)))

    def __truediv__(self, divisor: int | Decimal | float) -> 'Money':
        return Money(self.amount / Decimal(str(divisor)))

    def __str__(self) -> str:
        return f"${self.amount:.2f}"

    def __repr__(self) -> str:
        return f"Money({str(self.amount)})"

    def to_decimal(self) -> Decimal:
        return self.amount
    
    def dict(self):
        """Make Money objects JSON serializable."""
        return {
            "amount": str(self.amount),
            "cents": self.to_cents()
        }
    
    def __float__(self):
        """Allow conversion to float for JSON serialization."""
        return float(self.amount)
    
    def __str__(self):
        return f"${self.amount:.2f}"
