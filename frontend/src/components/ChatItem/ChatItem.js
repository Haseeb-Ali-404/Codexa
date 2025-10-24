import React from "react";
import PropTypes from "prop-types";

const ChatItem = ({ title, active, onClick }) => {
  return (
    <div
      className={`chat-item ${active ? "active" : ""}`}
      onClick={onClick}
      title={title}
    >
      <span className="chat-item-title">{title}</span>
    </div>
  );
};

ChatItem.propTypes = {
  title: PropTypes.string.isRequired,
  active: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
};

ChatItem.defaultProps = {
  active: false,
};

export default ChatItem;
