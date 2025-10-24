// src/components/RecentProjects.js
import React from "react";
import PropTypes from "prop-types";
import "./RecentProjects.css";

const RecentProjects = ({ projects }) => {
  return (
    <div className="recent-projects-container">
      {projects.length === 0 ? (
        <p className="no-projects">No recent projects found</p>
      ) : (
        <div className="projects-grid">
          {projects.map((project) => (
            <div key={project.id} className="project-card">
              {project.image ? (
                <img
                  src={project.image}
                  alt={project.name}
                  className="project-image"
                />
              ) : (
                <div className="project-preview">
                  {project.preview || "Preview unavailable"}
                </div>
              )}
              <div className="project-name">{project.name}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

RecentProjects.propTypes = {
  projects: PropTypes.arrayOf(
    PropTypes.shape({
      id: PropTypes.string.isRequired,
      name: PropTypes.string.isRequired,
      image: PropTypes.string,
      preview: PropTypes.string,
    })
  ).isRequired,
};

export default RecentProjects;
