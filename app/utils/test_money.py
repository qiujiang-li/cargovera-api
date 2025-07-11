import pytest
from decimal import Decimal
from money import Money

def test_create_money_from_string():
    m = Money("19.99")
    assert m.amount == Decimal("19.99")

def test_create_money_from_float():
    m = Money(19.99)
    assert m.amount == Decimal("19.99")

def test_from_cents_and_to_cents():
    m = Money.from_cents(1999)
    assert m.amount == Decimal("19.99")
    assert m.to_cents() == 1999

def test_addition():
    m1 = Money("10.00")
    m2 = Money("5.50")
    result = m1 + m2
    assert result.amount == Decimal("15.50")

def test_subtraction():
    m1 = Money("10.00")
    m2 = Money("4.25")
    result = m1 - m2
    assert result.amount == Decimal("5.75")

def test_multiplication_with_decimal():
    m = Money("10.00")
    result = m * Decimal("1.5")
    assert result.amount == Decimal("15.00")

def test_multiplication_with_float():
    m = Money("10.00")
    result = m * 2.5
    assert result.amount == Decimal("25.00")

def test_division():
    m = Money("10.00")
    result = m / 4
    assert result.amount == Decimal("2.50")

def test_str_and_repr():
    m = Money("19.99")
    assert str(m) == "$19.99"
    assert repr(m) == "Money(19.99)"

def test_cents_to_dollars():
    m = Money.from_cents(1999)  
    assert m.amount == Decimal("19.99")

def test_dollars_to_cents():    
    m = Money("19.99")
    assert m.to_cents() == 1999

def main():
    test_create_money_from_string()
    test_create_money_from_float()
    test_from_cents_and_to_cents()
    test_addition()
    test_subtraction()
    test_multiplication_with_decimal()
    test_multiplication_with_float()   
    test_division()
    test_str_and_repr()
    test_cents_to_dollars()
    test_dollars_to_cents()

if __name__ == "__main__":
    main()
