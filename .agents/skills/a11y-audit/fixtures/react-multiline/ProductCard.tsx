import React from 'react';

export function ProductCard({ product }) {
  return (
    <article>
      <img
        src={product.image}
        className="w-full rounded-lg"
      />
      <h2>{product.name}</h2>
      <div
        onClick={() => navigate(`/product/${product.id}`)}
        className="card-footer"
        role="button"
      >
        View details
      </div>
      <button
        style={{
          outline: 'none',
          border: 'none',
        }}
      >
        Add to cart
      </button>
      <p className="text-gray-400">
        Limited stock
      </p>
    </article>
  );
}
